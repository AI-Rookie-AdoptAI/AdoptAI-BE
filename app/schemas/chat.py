from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.slots import ApiSlots


class Stage(str, Enum):
    START = "start"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    CLARIFYING = "clarifying"
    DRAFT_READY = "draft_ready"
    EDITING = "editing"
    PUBLISHING = "publishing"
    PUBLISHED = "published"


class MessageType(str, Enum):
    TEXT = "text"
    VOICE = "voice"
    IMAGE_GROUP = "image_group"
    PET_INFO_CARD = "pet_info_card"
    DRAFT_CARD = "draft_card"
    QUICK_CHIPS = "quick_chips"
    FACT_BADGE = "fact_badge"
    QUICK_REPLY = "quick_reply"


class ApiDraftPetInfo(ApiSlots):
    name: str | None = None
    species: Literal["dog", "cat", "other"] = "dog"


class ApiDraft(BaseModel):
    pet_name: str
    title: str
    description: str
    pet_info: ApiDraftPetInfo
    representative_photo: str | None = None


class ParsedPetInfo(ApiSlots):
    species: Literal["dog", "cat", "other"] | None = None


class ApiMessage(BaseModel):
    id: str
    role: str
    type: MessageType
    content: str
    metadata: dict[str, Any] | None = None
    created_at: datetime


class SessionResponse(BaseModel):
    id: str
    stage: Stage
    announcement_id: str | None = None
    created_at: datetime


class SendMessageRequest(BaseModel):
    type: MessageType = MessageType.TEXT
    content: str
    metadata: dict[str, Any] | None = None


class ChatMessageResponse(BaseModel):
    user_message: ApiMessage
    assistant_messages: list[ApiMessage]
    stage: Stage
    draft: ApiDraft | None = None


class ImageUploadResponse(BaseModel):
    assistant_messages: list[ApiMessage]
    stage: Stage
    representative_index: int = 0
    ai_confidence: int = 0
    parsed_pet_info: ParsedPetInfo | None = None


class PublishRequest(BaseModel):
    platform_id: str | None = None


class PublishResponse(BaseModel):
    announcement_id: str
    time_taken: str
