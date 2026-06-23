from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class AnnouncementStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    CLOSED = "closed"


class PetInfo(BaseModel):
    species: str
    breed: str | None = None
    gender: Literal["male", "female", "unknown"]
    estimated_age: str | None = None
    weight: str | None = None
    health_conditions: list[str] = []
    neutered: bool | None = None
    vaccinated: bool | None = None
    characteristics: list[str] = []


class AnnouncementResponse(BaseModel):
    id: str
    status: AnnouncementStatus
    pet_info: PetInfo | None = None
    photos: list[str] = []
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class AnnouncementDetailResponse(AnnouncementResponse):
    chat_session_id: str | None = None


class AnnouncementUpdate(BaseModel):
    pet_info: PetInfo | None = None
    description: str | None = None


class AnnouncementListResponse(BaseModel):
    items: list[AnnouncementResponse]
    total: int
    page: int
    size: int


class PublishResponse(BaseModel):
    id: str
    status: AnnouncementStatus
    updated_at: datetime
