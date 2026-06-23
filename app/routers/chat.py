import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.announcement import Announcement
from app.models.chat import ChatSession, Message
from app.models.user import User
from app.schemas.chat import (
    ConfirmRequest,
    ConfirmResponse,
    CreateSessionRequest,
    ImageUploadResponse,
    MessageListResponse,
    MessageResponse,
    MessageType,
    SendMessageRequest,
    SendMessageResponse,
    SessionResponse,
    VoiceResponse,
)
from app.services import ai as ai_service
from app.services.storage import save_file

router = APIRouter(prefix="/chat", tags=["Chat"])

_GREETING = "안녕하세요! 입양 공고 작성을 도와드릴게요. 반려동물에 대해 편하게 말씀해 주세요."


def _msg_to_schema(msg: Message) -> MessageResponse:
    return MessageResponse(
        id=msg.id,
        role=msg.role,
        type=MessageType(msg.type),
        content=msg.content,
        metadata=msg.extra,
        created_at=msg.created_at,
    )


async def _get_session(session_id: str, db: AsyncSession, user: User) -> ChatSession:
    """Fetch a chat session that belongs to the current user (via announcement)."""
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
    """Return conversation history in LLM-friendly format."""
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
    )
    return [{"role": m.role, "content": m.content} for m in result.scalars().all()]


async def _save_message(
    session_id: str,
    role: str,
    type: MessageType,
    content: str,
    extra: dict | None,
    db: AsyncSession,
) -> Message:
    msg = Message(
        session_id=session_id,
        role=role,
        type=type.value,
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
    summary="채팅 세션 시작",
    description="새 채팅 세션을 생성합니다. announcement_id가 없으면 새 공고 초안을 자동 생성합니다.",
)
async def create_session(
    body: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionResponse:
    announcement_id = body.announcement_id

    if announcement_id:
        ann_result = await db.execute(
            select(Announcement).where(
                Announcement.id == announcement_id,
                Announcement.user_id == current_user.id,
            )
        )
        if not ann_result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="공고를 찾을 수 없습니다")
    else:
        ann = Announcement(user_id=current_user.id)
        db.add(ann)
        await db.flush()
        announcement_id = ann.id

    session = ChatSession(announcement_id=announcement_id)
    db.add(session)
    await db.flush()

    greeting = await _save_message(
        session.id, "assistant", MessageType.TEXT, _GREETING, None, db
    )

    ann_update = await db.execute(select(Announcement).where(Announcement.id == announcement_id))
    ann_obj = ann_update.scalar_one()
    ann_obj.chat_session_id = session.id
    ann_obj.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(session)
    await db.refresh(greeting)

    return SessionResponse(
        id=session.id,
        announcement_id=session.announcement_id,
        status=session.status,
        messages=[_msg_to_schema(greeting)],
        created_at=session.created_at,
    )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=MessageListResponse,
    summary="메시지 목록 조회",
    description="커서 기반 페이지네이션으로 이전 메시지를 조회합니다.",
)
async def list_messages(
    session_id: str,
    before: str | None = Query(None, description="이 메시지 ID 이전의 메시지 조회"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageListResponse:
    await _get_session(session_id, db, current_user)

    query = select(Message).where(Message.session_id == session_id)

    if before:
        cursor_result = await db.execute(select(Message).where(Message.id == before))
        cursor_msg = cursor_result.scalar_one_or_none()
        if cursor_msg:
            query = query.where(Message.created_at < cursor_msg.created_at)

    query = query.order_by(Message.created_at.desc()).limit(limit + 1)
    result = await db.execute(query)
    rows = result.scalars().all()

    has_more = len(rows) > limit
    items = [_msg_to_schema(m) for m in reversed(rows[:limit])]
    return MessageListResponse(items=items, has_more=has_more)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=SendMessageResponse,
    summary="텍스트 메시지 전송",
    description="사용자 텍스트를 전송하고 AI 응답을 받습니다.",
)
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SendMessageResponse:
    await _get_session(session_id, db, current_user)
    history = await _get_history(session_id, db)

    user_msg = await _save_message(session_id, "user", body.type, body.content, None, db)

    history.append({"role": "user", "content": body.content})
    ai_response = await ai_service.process_text_message(body.content, history)

    assistant_msg = await _save_message(
        session_id, "assistant", ai_response.type, ai_response.content, ai_response.metadata, db
    )

    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)

    return SendMessageResponse(
        user_message=_msg_to_schema(user_msg),
        assistant_message=_msg_to_schema(assistant_msg),
    )


@router.post(
    "/sessions/{session_id}/voice",
    response_model=VoiceResponse,
    summary="음성 메모 업로드",
    description="음성 파일을 업로드하면 STT 변환 후 AI가 분석합니다.",
)
async def upload_voice(
    session_id: str,
    audio: UploadFile = File(..., description=".m4a / .mp3 / .wav / .webm"),
    duration: float = Form(..., description="녹음 길이 (초)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VoiceResponse:
    await _get_session(session_id, db, current_user)

    audio_url, _ = await save_file(audio, "audio")
    history = await _get_history(session_id, db)

    transcribed, ai_response = await ai_service.transcribe_and_process(audio_url, duration, history)

    voice_msg = await _save_message(
        session_id,
        "user",
        MessageType.VOICE,
        "음성 메모",
        {"voice_duration": duration, "audio_url": audio_url},
        db,
    )
    assistant_msg = await _save_message(
        session_id, "assistant", ai_response.type, ai_response.content, ai_response.metadata, db
    )

    await db.commit()
    await db.refresh(voice_msg)
    await db.refresh(assistant_msg)

    return VoiceResponse(
        voice_message=_msg_to_schema(voice_msg),
        assistant_message=_msg_to_schema(assistant_msg),
    )


@router.post(
    "/sessions/{session_id}/image",
    response_model=ImageUploadResponse,
    summary="사진 업로드",
    description="반려동물 사진을 업로드하면 AI가 분석합니다.",
)
async def upload_image(
    session_id: str,
    image: UploadFile = File(..., description=".jpg / .jpeg / .png / .webp"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImageUploadResponse:
    await _get_session(session_id, db, current_user)

    image_url, _ = await save_file(image, "images")
    history = await _get_history(session_id, db)

    ai_response = await ai_service.analyze_image(image_url, history)

    image_msg = await _save_message(
        session_id,
        "user",
        MessageType.IMAGE,
        "사진",
        {"image_url": image_url},
        db,
    )
    assistant_msg = await _save_message(
        session_id, "assistant", ai_response.type, ai_response.content, ai_response.metadata, db
    )

    await db.commit()
    await db.refresh(image_msg)
    await db.refresh(assistant_msg)

    return ImageUploadResponse(
        image_message=_msg_to_schema(image_msg),
        assistant_message=_msg_to_schema(assistant_msg),
    )


@router.post(
    "/sessions/{session_id}/confirm",
    response_model=ConfirmResponse,
    summary="확인 질문 답변",
    description="AI 확인 질문에 대한 답변(true/false 또는 string)을 전송합니다.",
)
async def confirm(
    session_id: str,
    body: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConfirmResponse:
    await _get_session(session_id, db, current_user)
    history = await _get_history(session_id, db)

    ai_response = await ai_service.process_confirmation(body.question_id, body.answer, history)

    answer_content = str(body.answer)
    await _save_message(session_id, "user", MessageType.TEXT, answer_content, None, db)

    assistant_msg = await _save_message(
        session_id, "assistant", ai_response.type, ai_response.content, ai_response.metadata, db
    )

    await db.commit()
    await db.refresh(assistant_msg)

    return ConfirmResponse(assistant_message=_msg_to_schema(assistant_msg))
