"""
AI service — Anthropic Claude 연동.
현재는 stub 구현. TODO 주석에 실제 API 호출 예시 포함.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.schemas.chat import ApiDraft, ApiDraftPetInfo, ApiMessage, MessageType, ParsedPetInfo, Stage
from app.schemas.slots import AgeValue


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


async def process_text_message(
    content: str,
    history: list[dict],
    message_type: MessageType = MessageType.TEXT,
    metadata: dict | None = None,
) -> tuple[list[ApiMessage], Stage, ApiDraft | None]:
    """
    텍스트/quick_reply 메시지를 처리하고 (assistant_messages, stage, draft)를 반환.

    TODO: Anthropic tool_use 기반 구현 예시:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=history,
            tools=[PET_INFO_TOOL, DRAFT_TOOL],
        )
        # tool_use block이면 draft 파싱, 아니면 text 응답
    """
    if message_type == MessageType.QUICK_REPLY:
        question_key = (metadata or {}).get("question_key", "")
        if question_key == "neutered":
            reply = _msg(MessageType.TEXT, "확인했어요! 예방접종 여부도 알려주시겠어요?", {
                "chips": [
                    {"label": "완료", "value": "true"},
                    {"label": "미접종", "value": "false"},
                    {"label": "모름", "value": "unknown"},
                ],
                "question_key": "vaccinated",
                "current_question": 2,
                "total_questions": 3,
            })
            return [reply], Stage.CLARIFYING, None
        # 마지막 질문 답변 → 초안 생성
        draft = ApiDraft(
            pet_name="이름 없음",
            title="[임시] 반려동물 입양 공고",
            description="공고 내용을 입력해 주세요.",
            pet_info=ApiDraftPetInfo(species="dog"),
        )
        card = _msg(MessageType.DRAFT_CARD, "이렇게 작성했어요. 확인 후 게시해 주세요!", {
            "draft": draft.model_dump(),
        })
        return [card], Stage.DRAFT_READY, draft

    # 일반 텍스트 응답
    chips = _msg(MessageType.QUICK_CHIPS, "중성화 수술을 했나요?", {
        "chips": [
            {"label": "했어요", "value": "true"},
            {"label": "안 했어요", "value": "false"},
            {"label": "모름", "value": "unknown"},
        ],
        "question_key": "neutered",
        "current_question": 1,
        "total_questions": 3,
    })
    return [chips], Stage.CLARIFYING, None


async def process_images(
    image_urls: list[str],
    history: list[dict],
) -> tuple[list[ApiMessage], Stage, int, int, ParsedPetInfo | None]:
    """
    이미지를 분석하고 (assistant_messages, stage, rep_index, confidence, parsed_pet_info) 반환.

    TODO: Claude vision 예시:
        import base64, httpx
        images_b64 = []
        async with httpx.AsyncClient() as client:
            for url in image_urls:
                r = await client.get(url)
                images_b64.append(base64.b64encode(r.content).decode())

        content_blocks = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}
            for b64 in images_b64
        ]
        content_blocks.append({"type": "text", "text": "이 반려동물 사진을 분석해주세요."})
        response = await client.messages.create(
            model="claude-sonnet-4-5", max_tokens=512, messages=[{"role": "user", "content": content_blocks}]
        )
    """
    representative_index = 0
    ai_confidence = 85
    parsed = ParsedPetInfo(
        species="dog",
        breed="믹스견",
        sex="미상",
        estimated_age=AgeValue(value=3, unit="년"),
    )

    msg = _msg(MessageType.PET_INFO_CARD, "사진에서 정보를 추출했어요!", {
        "image_urls": image_urls,
        "ai_pick_index": representative_index,
        "ai_confidence": ai_confidence,
        "pet_info": parsed.model_dump(),
    })
    return [msg], Stage.CLARIFYING, representative_index, ai_confidence, parsed


async def transcribe_and_process(
    audio_url: str,
    duration_sec: float,
    history: list[dict],
) -> tuple[str, list[ApiMessage], Stage, ApiDraft | None]:
    """
    음성을 STT로 전사 후 LLM으로 처리. (transcribed, assistant_messages, stage, draft) 반환.

    TODO: OpenAI Whisper 예시:
        import openai
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        async with httpx.AsyncClient() as hc:
            audio_bytes = (await hc.get(audio_url)).content
        transcript = await client.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.webm", audio_bytes, "audio/webm"),
        )
        transcribed = transcript.text
        messages, stage, draft = await process_text_message(transcribed, history)
        return transcribed, messages, stage, draft
    """
    transcribed = "음성이 텍스트로 변환되었습니다 (stub)."
    msgs, stage, draft = await process_text_message(transcribed, history)
    return transcribed, msgs, stage, draft


async def publish_draft(
    draft: dict,
    platform_id: str | None,
    announcement_id: str,
) -> str:
    """
    초안을 플랫폼에 게시. 소요 시간 문자열 반환.

    TODO: 플랫폼별 API 연동 또는 이메일/슬랙 알림 발송.
    """
    return "1분 42초"
