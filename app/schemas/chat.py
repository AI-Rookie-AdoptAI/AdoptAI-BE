from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class MessageType(str, Enum):
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"
    PET_INFO_CARD = "pet_info_card"
    CONFIRMATION_QUESTION = "confirmation_question"


class MessageResponse(BaseModel):
    id: str
    role: str
    type: MessageType
    content: str
    metadata: dict | None = None
    created_at: datetime


class SessionResponse(BaseModel):
    id: str
    announcement_id: str | None = None
    status: str
    messages: list[MessageResponse] = []
    created_at: datetime


class CreateSessionRequest(BaseModel):
    announcement_id: str | None = None


class SendMessageRequest(BaseModel):
    type: MessageType = MessageType.TEXT
    content: str


class SendMessageResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse


class ConfirmRequest(BaseModel):
    question_id: str
    answer: bool | str


class ConfirmResponse(BaseModel):
    assistant_message: MessageResponse


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    has_more: bool


class VoiceResponse(BaseModel):
    voice_message: MessageResponse
    assistant_message: MessageResponse


class ImageUploadResponse(BaseModel):
    image_message: MessageResponse
    assistant_message: MessageResponse
