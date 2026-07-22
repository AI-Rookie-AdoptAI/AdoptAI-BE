from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.slots import ApiSlots, Species


class AnnouncementStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    CLOSED = "closed"


class AnnouncementPetInfo(ApiSlots):
    name: str | None = None
    species: Species = "dog"


class ApiDraftInAnnouncement(BaseModel):
    pet_name: str
    title: str
    description: str
    pet_info: AnnouncementPetInfo
    representative_photo: str | None = None


class PlatformVariant(BaseModel):
    title: str
    body: str
    info_table: dict[str, str] = Field(default_factory=dict)
    platform: Literal["instagram", "daangn", "naver_cafe"]
    faithfulness: dict[str, Any] | None = None
    edited: bool = False


class GeneratePlatformDraftsRequest(BaseModel):
    platforms: list[Literal["instagram", "daangn", "naver_cafe"]] = Field(
        min_length=1,
        max_length=3,
    )


class GeneratePlatformDraftsResponse(BaseModel):
    variants: dict[str, PlatformVariant]


class ApiAnnouncement(BaseModel):
    id: str
    status: AnnouncementStatus
    title: str | None = None
    description: str | None = None
    photos: list[str] = Field(default_factory=list)
    platform_id: str | None = None
    session_id: str | None = None  # draft 상태에서만 포함
    created_at: datetime
    updated_at: datetime
    pet_info: AnnouncementPetInfo | None = None
    draft: ApiDraftInAnnouncement | None = None
    platform_variants: dict[str, PlatformVariant] = Field(default_factory=dict)


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
