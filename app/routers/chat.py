import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.announcement import Announcement
from app.models.chat import ChatSession, Message
from app.models.user import User
from app.schemas.chat import (
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
from app.services.storage import save_file

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
    ann.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(session)

    return SessionResponse(
        id=session.id,
        stage=Stage.START,
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
    await _require_session(session_id, db, current_user)
    history = await _get_history(session_id, db)

    user_row = await _persist_message(
        session_id, "user", body.type, body.content, body.metadata, db
    )
    history.append({"role": "user", "content": body.content})

    ai_msgs, stage, draft = await ai_service.process_text_message(
        body.content, history, body.type, body.metadata
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
    await _require_session(session_id, db, current_user)
    history = await _get_history(session_id, db)

    user_row = await _persist_message(
        session_id, "user", body.type, body.content, body.metadata, db
    )
    history.append({"role": "user", "content": body.content})

    ai_msgs, stage, draft = await ai_service.process_text_message(
        body.content, history, body.type, body.metadata
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

    full_content = " ".join(m.content for m in ai_msgs)

    async def event_generator():
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

    await _require_session(session_id, db, current_user)
    history = await _get_history(session_id, db)

    image_urls: list[str] = []
    for img in images:
        url, _ = await save_file(img, "images")
        image_urls.append(url)

    ai_msgs, stage, rep_idx, confidence, parsed_pet_info = await ai_service.process_images(
        image_urls, history
    )

    for ai_msg in ai_msgs:
        await _persist_message(
            session_id, "assistant", ai_msg.type, ai_msg.content, ai_msg.metadata, db
        )

    await db.commit()

    return ImageUploadResponse(
        assistant_messages=ai_msgs,
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
    await _require_session(session_id, db, current_user)
    history = await _get_history(session_id, db)

    audio_url, _ = await save_file(audio, "audio")
    duration_float = float(duration_sec)

    transcribed, ai_msgs, stage, draft = await ai_service.transcribe_and_process(
        audio_url, duration_float, history
    )

    user_row = await _persist_message(
        session_id,
        "user",
        MessageType.VOICE,
        transcribed,
        {"voice_duration": duration_float, "audio_url": audio_url},
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
    session = await _require_session(session_id, db, current_user)

    if not session.announcement_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="세션에 연결된 공고가 없습니다")

    ann_result = await db.execute(
        select(Announcement).where(Announcement.id == session.announcement_id)
    )
    ann = ann_result.scalar_one()

    time_taken = await ai_service.publish_draft(
        ann.pet_info or {},
        body.platform_id,
        ann.id,
        body.custom_platform.model_dump() if body.custom_platform else None,
    )

    ann.status = "published"
    ann.platform_id = body.platform_id
    ann.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return PublishResponse(
        announcement_id=ann.id,
        time_taken=time_taken,
    )
