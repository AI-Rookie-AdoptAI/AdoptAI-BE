"""Chat-facing orchestration for STT, notice generation, and Vision results."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import UploadFile

from app.schemas.chat import ApiDraft, ApiDraftPetInfo, ApiMessage, MessageType, ParsedPetInfo, Stage
from app.schemas.slots import Species
from app.services import stt as stt_service
from app.services import vision as vision_service


def _now() -> datetime:
    return datetime.now(UTC)


def _msg(
    type: MessageType,
    content: str,
    metadata: dict | None = None,
) -> ApiMessage:
    return ApiMessage(
        id=f"msg_{uuid.uuid4().hex[:12]}",
        role="assistant",
        type=type,
        content=content,
        metadata=metadata,
        created_at=_now(),
    )


async def process_images(
    image_urls: list[str],
    local_paths: list[str],
    _history: list[dict],
) -> tuple[list[ApiMessage], Stage, int, int, ParsedPetInfo | None]:
    """
    이미지를 분석하고 (assistant_messages, stage, rep_index, confidence, parsed_pet_info) 반환.

    대표사진 선택은 ../VISION (frozen CLIP L/14 → student MLP + SVR 앙상블)을 사용한다.
    품종/나이 등 pet_info는 별도 분석 모델이 없으므로 추측하지 않는다.
    """
    representative_index, ai_confidence = await vision_service.select_representative(local_paths)
    parsed = None
    msg = _msg(MessageType.TEXT, "대표 사진을 골랐어요. 이제 아이의 특징과 구조 당시 상황을 알려주세요.", {
        "image_urls": image_urls,
        "ai_pick_index": representative_index,
        "ai_confidence": ai_confidence,
    })
    return [msg], Stage.CLARIFYING, representative_index, ai_confidence, parsed


def _slot_chips(slot: str) -> list[dict] | None:
    if slot == "is_neutered":
        return [
            {"label": "했어요", "value": "했어요"},
            {"label": "안 했어요", "value": "안 했어요"},
            {"label": "모름", "value": "모름"},
        ]
    if slot == "sex":
        return [{"label": value, "value": value} for value in ("수컷", "암컷", "미상")]
    return None


def pipeline_messages(payload: dict) -> tuple[list[ApiMessage], Stage]:
    """Convert an STT pipeline response to the stable chat response contract."""
    question = payload.get("question")
    missing = payload.get("missing_slots") or []
    if question:
        slot = payload.get("pending_slot") or (missing[0] if missing else "unknown")
        metadata: dict = {"question_key": slot}
        chips = _slot_chips(slot)
        if chips:
            metadata["chips"] = chips
            return [_msg(MessageType.QUICK_CHIPS, question, metadata)], Stage.CLARIFYING
        return [_msg(MessageType.TEXT, question, metadata)], Stage.CLARIFYING
    return [], Stage.DRAFT_READY if payload.get("ready_for_notice") else Stage.PROCESSING


def _as_species(value: object) -> Species:
    """LLM/STT가 돌려준 값이 허용 범위를 벗어나면 other로 떨어뜨린다."""
    if value == "dog":
        return "dog"
    if value == "cat":
        return "cat"
    return "other"


def draft_from_completion(payload: dict) -> ApiDraft:
    slots = dict(payload.get("slots") or {})
    pet_name = slots.pop("name", None) or "이름 없음"
    species = _as_species(slots.pop("species", None))
    notice = payload.get("notice") or {}
    return ApiDraft(
        pet_name=pet_name,
        title=notice.get("title") or "입양 공고",
        description=notice.get("body") or "",
        pet_info=ApiDraftPetInfo(
            name=None if pet_name == "이름 없음" else pet_name,
            species=species,
            **slots,
        ),
    )


async def transcribe_and_process(
    audio: UploadFile,
    _duration_sec: float,
    _history: list[dict],
) -> tuple[str, dict, list[ApiMessage], Stage]:
    """Dedicated STT service에서 전사하고 슬롯 파이프라인을 시작한다."""
    payload = await stt_service.transcribe_and_start(audio)
    transcribed = payload.get("stt_text", "")
    msgs, stage = pipeline_messages(payload)
    return transcribed, payload, msgs, stage
