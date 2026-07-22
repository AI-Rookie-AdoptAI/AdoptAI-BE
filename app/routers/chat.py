import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.dependencies import get_current_user
from app.domain.chat_workflow import can_generate_platform_drafts
from app.models.announcement import Announcement
from app.models.chat import ChatSession, Message
from app.models.user import User
from app.schemas.announcement import (
    GeneratePlatformDraftsRequest,
    GeneratePlatformDraftsResponse,
    PlatformVariant,
)
from app.schemas.chat import (
    ApiDraft,
    ApiMessage,
    ChatMessageResponse,
    ImageUploadResponse,
    MessageType,
    PublishRequest,
    PublishResponse,
    SendMessageRequest,
    SessionResponse,
    Stage,
)
from app.services import ai as ai_service
from app.services import stt as stt_service
from app.services.storage import FileTooLargeError, delete_file, discard_local, local_path, save_file

router = APIRouter(prefix="/chat", tags=["Chat"])


def _msg_to_schema(msg: Message) -> ApiMessage:
    return ApiMessage(
        id=msg.id,
        role=msg.role,
        type=MessageType(msg.type),
        content=msg.content,
        metadata=msg.extra,
        created_at=msg.created_at,
    )


async def _require_session(session_id: str, db: AsyncSession, user: User) -> ChatSession:
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다")

    if session.announcement_id:
        ann_result = await db.execute(
            select(Announcement).where(
                Announcement.id == session.announcement_id,
                Announcement.user_id == user.id,
            )
        )
        if not ann_result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="접근 권한이 없습니다")

    return session


async def _get_history(session_id: str, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
    )
    return [{"role": m.role, "content": m.content} for m in result.scalars().all()]


def _ensure_session_writable(session: ChatSession) -> None:
    if session.stage in {Stage.PUBLISHING.value, Stage.PUBLISHED.value}:
        raise HTTPException(status_code=409, detail="완료된 채팅 세션에는 내용을 추가할 수 없습니다")


async def _persist_message(
    session_id: str,
    role: str,
    msg_type: MessageType,
    content: str,
    extra: dict | None,
    db: AsyncSession,
) -> Message:
    msg = Message(
        session_id=session_id,
        role=role,
        type=msg_type.value,
        content=content,
        extra=extra,
    )
    db.add(msg)
    await db.flush()
    return msg


async def _persist_draft(
    session: ChatSession,
    draft: ApiDraft,
    db: AsyncSession,
) -> None:
    """Keep the announcement and chat workflow in sync as one transaction."""
    if not session.announcement_id:
        return
    result = await db.execute(
        select(Announcement).where(Announcement.id == session.announcement_id)
    )
    announcement = result.scalar_one()
    if not draft.representative_photo and announcement.photos:
        draft.representative_photo = announcement.photos[0]
    payload = draft.model_dump(mode="json")
    announcement.title = draft.title
    announcement.description = draft.description
    announcement.pet_info = payload["pet_info"]
    announcement.draft = payload
    announcement.updated_at = datetime.now(UTC)


async def _process_user_input(
    session: ChatSession,
    content: str,
    message_type: MessageType,
    metadata: dict | None,
    history: list[dict],
) -> tuple[list[ApiMessage], Stage, ApiDraft | None]:
    """Route initial typed input and follow-up answers through one STT slot pipeline."""
    pipeline: dict | None = None
    if session.stt_session_id and session.stage == Stage.CLARIFYING.value:
        pipeline = await stt_service.answer(session.stt_session_id, content)
    elif session.stage in {
        Stage.START.value,
        Stage.UPLOADING.value,
        Stage.PROCESSING.value,
        Stage.CLARIFYING.value,
    }:
        pipeline = await stt_service.start(content)
        session.stt_session_id = pipeline["session_id"]

    if pipeline is None:
        if session.stage in {Stage.DRAFT_READY.value, Stage.EDITING.value}:
            return [ai_service._msg(
                MessageType.TEXT,
                "초안이 이미 완성됐어요. 공고 이름과 내용은 내 공고 화면에서 수정할 수 있어요.",
            )], Stage.DRAFT_READY, None
        return [ai_service._msg(
            MessageType.TEXT,
            "이 단계에서는 새 정보를 처리할 수 없어요. 새 공고 작성을 시작해 주세요.",
        )], Stage(session.stage), None

    session.stt_slots = pipeline.get("slots")
    ai_msgs, stage = ai_service.pipeline_messages(pipeline)
    draft = None
    if pipeline.get("completed") and pipeline.get("ready_for_notice") and session.stt_session_id:
        completed = await stt_service.complete(session.stt_session_id)
        draft = ai_service.draft_from_completion(completed)
        ai_msgs.append(ai_service._msg(
            MessageType.DRAFT_CARD,
            "공고 초안을 만들었어요. 내용을 확인해 주세요!",
            {"draft": draft.model_dump(mode="json")},
        ))
        stage = Stage.DRAFT_READY
    return ai_msgs, stage, draft


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="채팅 세션 생성",
)
async def create_session(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionResponse:
    ann = Announcement(user_id=current_user.id)
    db.add(ann)
    await db.flush()

    session = ChatSession(announcement_id=ann.id)
    db.add(session)
    await db.flush()

    ann.chat_session_id = session.id
    ann.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(session)

    return SessionResponse(
        id=session.id,
        stage=Stage(session.stage),
        announcement_id=session.announcement_id,
        created_at=session.created_at,
    )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    summary="채팅 세션 진행 상태 조회",
)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionResponse:
    session = await _require_session(session_id, db, current_user)
    return SessionResponse(
        id=session.id,
        stage=Stage(session.stage),
        announcement_id=session.announcement_id,
        created_at=session.created_at,
    )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ApiMessage],
    summary="세션 메시지 목록 (재접속 복원용)",
)
async def list_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ApiMessage]:
    await _require_session(session_id, db, current_user)
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
    )
    return [_msg_to_schema(m) for m in result.scalars().all()]


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageResponse,
    summary="텍스트 / quick_reply 메시지 전송",
)
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessageResponse:
    session = await _require_session(session_id, db, current_user)
    _ensure_session_writable(session)
    history = await _get_history(session_id, db)

    user_row = await _persist_message(
        session_id, "user", body.type, body.content, body.metadata, db
    )
    history.append({"role": "user", "content": body.content})

    try:
        ai_msgs, stage, draft = await _process_user_input(
            session, body.content, body.type, body.metadata, history
        )
    except stt_service.SttServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    session.stage = stage.value
    if draft:
        await _persist_draft(session, draft, db)

    assistant_rows: list[Message] = []
    for ai_msg in ai_msgs:
        row = await _persist_message(
            session_id, "assistant", ai_msg.type, ai_msg.content, ai_msg.metadata, db
        )
        assistant_rows.append(row)

    await db.commit()
    await db.refresh(user_row)
    for row in assistant_rows:
        await db.refresh(row)

    return ChatMessageResponse(
        user_message=_msg_to_schema(user_row),
        assistant_messages=[_msg_to_schema(r) for r in assistant_rows],
        stage=stage,
        draft=draft,
    )


@router.post(
    "/sessions/{session_id}/platform-drafts",
    response_model=GeneratePlatformDraftsResponse,
    summary="완성된 슬롯으로 플랫폼별 공고 생성",
)
async def generate_platform_drafts(
    session_id: str,
    body: GeneratePlatformDraftsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GeneratePlatformDraftsResponse:
    session = await _require_session(session_id, db, current_user)
    if not session.announcement_id or not session.stt_slots:
        raise HTTPException(status_code=409, detail="플랫폼별 공고를 만들 슬롯 정보가 없습니다")
    ann_result = await db.execute(
        select(Announcement).where(Announcement.id == session.announcement_id)
    )
    announcement = ann_result.scalar_one()
    if not can_generate_platform_drafts(session.stage, has_draft=bool(announcement.draft)):
        raise HTTPException(status_code=409, detail="초안이 완성된 뒤 플랫폼별 공고를 만들 수 있습니다")

    try:
        payload = await stt_service.generate_all(session.stt_slots)
    except stt_service.SttServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    notices = payload.get("notices") or {}
    variants: dict[str, PlatformVariant] = {}
    for platform in dict.fromkeys(body.platforms):
        notice = notices.get(platform)
        if not notice:
            raise HTTPException(status_code=502, detail=f"{platform} 공고 생성 결과가 없습니다")
        variants[platform] = PlatformVariant.model_validate(notice)

    draft_payload = dict(announcement.draft or {})
    draft_payload["platform_variants"] = {
        key: value.model_dump(mode="json") for key, value in variants.items()
    }
    announcement.draft = draft_payload
    announcement.status = "in_review"
    announcement.updated_at = datetime.now(UTC)
    await db.commit()

    return GeneratePlatformDraftsResponse(variants=variants)


@router.post(
    "/sessions/{session_id}/messages/stream",
    summary="SSE 스트리밍 텍스트 메시지",
    response_class=StreamingResponse,
)
async def stream_message(
    session_id: str,
    body: SendMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    session = await _require_session(session_id, db, current_user)
    _ensure_session_writable(session)
    history = await _get_history(session_id, db)

    user_row = await _persist_message(
        session_id, "user", body.type, body.content, body.metadata, db
    )
    history.append({"role": "user", "content": body.content})

    try:
        ai_msgs, stage, draft = await _process_user_input(
            session, body.content, body.type, body.metadata, history
        )
    except stt_service.SttServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    assistant_rows: list[Message] = []
    for ai_msg in ai_msgs:
        row = await _persist_message(
            session_id, "assistant", ai_msg.type, ai_msg.content, ai_msg.metadata, db
        )
        assistant_rows.append(row)

    session.stage = stage.value
    if draft:
        await _persist_draft(session, draft, db)

    await db.commit()
    await db.refresh(user_row)
    for row in assistant_rows:
        await db.refresh(row)

    full_content = " ".join(m.content for m in ai_msgs)

    async def event_generator() -> AsyncGenerator[str, None]:
        # 토큰 단위 스트리밍 (단어 단위 시뮬레이션)
        for word in full_content.split():
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps({'type': 'token', 'delta': word + ' '}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.05)

        # 완성된 메시지 이벤트
        for row in assistant_rows:
            msg_dict = _msg_to_schema(row).model_dump(mode="json")
            yield f"data: {json.dumps({'type': 'message', 'message': msg_dict}, ensure_ascii=False)}\n\n"

        # 종료 이벤트
        done_payload: dict = {"type": "done", "stage": stage.value, "draft": None}
        if draft:
            done_payload["draft"] = draft.model_dump(mode="json")
        yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post(
    "/sessions/{session_id}/images",
    response_model=ImageUploadResponse,
    summary="반려동물 사진 업로드 (1~10장)",
)
async def upload_images(
    session_id: str,
    images: list[UploadFile] = File(..., description="image/* 파일 1~10개"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImageUploadResponse:
    if not images or len(images) > 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미지는 1~10장 업로드 가능합니다")
    for image in images:
        if not (image.content_type or "").startswith("image/"):
            raise HTTPException(status_code=415, detail="지원하지 않는 이미지 형식입니다")
        if image.size is not None and image.size > settings.MAX_IMAGE_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="허용된 이미지 파일 크기를 초과했습니다")

    session = await _require_session(session_id, db, current_user)
    _ensure_session_writable(session)
    history = await _get_history(session_id, db)

    image_urls: list[str] = []
    local_paths: list[str] = []
    keys: list[str] = []
    try:
        for img in images:
            url, key = await save_file(
                img,
                "images",
                max_bytes=settings.MAX_IMAGE_UPLOAD_BYTES,
                # vision이 로컬 경로로 읽으므로 S3 백엔드에서도 사본을 남긴다.
                keep_local=True,
            )
            image_urls.append(url)
            keys.append(key)
            local_paths.append(local_path(key))
    except FileTooLargeError as exc:
        for key in keys:
            await delete_file(key)
        raise HTTPException(status_code=413, detail="허용된 이미지 파일 크기를 초과했습니다") from exc
    except Exception:
        for key in keys:
            await delete_file(key)
        raise

    try:
        ai_msgs, stage, rep_idx, confidence, parsed_pet_info = await ai_service.process_images(
            image_urls, local_paths, history
        )
    finally:
        for key in keys:
            discard_local(key)

    user_row = await _persist_message(
        session_id,
        "user",
        MessageType.IMAGE_GROUP,
        f"사진 {len(image_urls)}장을 업로드했어요.",
        {
            "image_urls": image_urls,
            "ai_pick_index": rep_idx,
            "ai_confidence": confidence,
        },
        db,
    )

    session.stage = stage.value
    if session.announcement_id:
        ann_result = await db.execute(
            select(Announcement).where(Announcement.id == session.announcement_id)
        )
        announcement = ann_result.scalar_one()
        announcement.photos = (
            [image_urls[rep_idx], *image_urls[:rep_idx], *image_urls[rep_idx + 1 :]]
            if 0 <= rep_idx < len(image_urls)
            else image_urls
        )
        if parsed_pet_info:
            announcement.pet_info = parsed_pet_info.model_dump(mode="json")
        announcement.updated_at = datetime.now(UTC)

    assistant_rows: list[Message] = []
    for ai_msg in ai_msgs:
        row = await _persist_message(
            session_id, "assistant", ai_msg.type, ai_msg.content, ai_msg.metadata, db
        )
        assistant_rows.append(row)

    await db.commit()
    await db.refresh(user_row)
    for row in assistant_rows:
        await db.refresh(row)

    return ImageUploadResponse(
        user_message=_msg_to_schema(user_row),
        assistant_messages=[_msg_to_schema(row) for row in assistant_rows],
        stage=stage,
        representative_index=rep_idx,
        ai_confidence=confidence,
        parsed_pet_info=parsed_pet_info,
    )


@router.post(
    "/sessions/{session_id}/voice",
    response_model=ChatMessageResponse,
    summary="음성 메모 업로드",
)
async def upload_voice(
    session_id: str,
    audio: UploadFile = File(..., description="audio/webm 또는 audio/mp4"),
    duration_sec: str = Form(..., description="녹음 길이 (초, 숫자 문자열)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessageResponse:
    session = await _require_session(session_id, db, current_user)
    _ensure_session_writable(session)
    history = await _get_history(session_id, db)

    try:
        duration_float = float(duration_sec)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="녹음 길이는 숫자여야 합니다") from exc
    if duration_float < 0 or duration_float > settings.MAX_AUDIO_DURATION_SECONDS:
        raise HTTPException(status_code=413, detail="허용된 녹음 시간을 초과했습니다")
    if audio.size is not None and audio.size > settings.MAX_AUDIO_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="허용된 오디오 파일 크기를 초과했습니다")
    if audio.content_type not in {
        "audio/webm", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav",
        "audio/ogg", "audio/flac", "video/webm", "video/mp4",
    }:
        raise HTTPException(status_code=415, detail="지원하지 않는 오디오 형식입니다")

    try:
        transcribed, pipeline, ai_msgs, stage = await ai_service.transcribe_and_process(
            audio, duration_float, history
        )
        session.stt_session_id = pipeline["session_id"]
        session.stt_slots = pipeline.get("slots")
        draft = None
        if pipeline.get("completed") and pipeline.get("ready_for_notice"):
            completed = await stt_service.complete(session.stt_session_id)
            draft = ai_service.draft_from_completion(completed)
            ai_msgs.append(ai_service._msg(
                MessageType.DRAFT_CARD,
                "공고 초안을 만들었어요. 내용을 확인해 주세요!",
                {"draft": draft.model_dump(mode="json")},
            ))
            stage = Stage.DRAFT_READY
    except stt_service.SttServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    session.stage = stage.value
    if draft:
        await _persist_draft(session, draft, db)

    user_row = await _persist_message(
        session_id,
        "user",
        MessageType.VOICE,
        transcribed,
        {"voice_duration": duration_float},
        db,
    )

    assistant_rows: list[Message] = []
    for ai_msg in ai_msgs:
        row = await _persist_message(
            session_id, "assistant", ai_msg.type, ai_msg.content, ai_msg.metadata, db
        )
        assistant_rows.append(row)

    await db.commit()
    await db.refresh(user_row)
    for row in assistant_rows:
        await db.refresh(row)

    return ChatMessageResponse(
        user_message=_msg_to_schema(user_row),
        assistant_messages=[_msg_to_schema(r) for r in assistant_rows],
        stage=stage,
        draft=draft,
    )


@router.post(
    "/sessions/{session_id}/publish",
    response_model=PublishResponse,
    summary="공고 게시",
)
async def publish(
    session_id: str,
    body: PublishRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PublishResponse:
    await _require_session(session_id, db, current_user)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "외부 플랫폼 자동 게시 기능은 아직 연결되지 않았습니다. "
            "플랫폼별 파일을 저장한 뒤 해당 플랫폼에서 직접 등록해 주세요."
        ),
    )
