from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.slots import ApiSlots


class AnnouncementStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    CLOSED = "closed"


class AnnouncementPetInfo(ApiSlots):
    name: str | None = None
    species: str = "dog"


class ApiDraftInAnnouncement(BaseModel):
    pet_name: str
    title: str
    description: str
    pet_info: AnnouncementPetInfo
    representative_photo: str | None = None


class ApiAnnouncement(BaseModel):
    id: str
    status: AnnouncementStatus
    title: str | None = None
    description: str | None = None
    photos: list[str] = []
    platform_id: str | None = None
    session_id: str | None = None  # draft 상태에서만 포함
    created_at: datetime
    updated_at: datetime
    pet_info: AnnouncementPetInfo | None = None
    draft: ApiDraftInAnnouncement | None = None


class AnnouncementListResponse(BaseModel):
    items: list[ApiAnnouncement]
    total: int
    page: int
    per_page: int


class AnnouncementUpdate(BaseModel):
    pet_info: AnnouncementPetInfo | None = None
    description: str | None = None
    title: str | None = None


class PublishAnnouncementResponse(BaseModel):
    id: str
    status: AnnouncementStatus
    updated_at: datetime
