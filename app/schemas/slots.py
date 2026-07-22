from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AgeValue(BaseModel):
    value: float
    unit: Literal["년", "개월", "일"]


class ContactMethod(BaseModel):
    type: Literal["phone", "instagram", "kakao", "other"]
    value: str


# AI가 만들어 오는 값이라 허용 범위를 한 곳에서만 정의하고 전 스키마가 공유한다.
Species = Literal["dog", "cat", "other"]


class ApiSlots(BaseModel):
    species: Species | None = None
    # 필수 슬롯
    breed: str | None = None
    estimated_age: AgeValue | None = None
    sex: Literal["수컷", "암컷", "미상"] | None = None
    is_neutered: bool | None = None
    weight_kg: float | None = None
    rescue_region: str | None = None
    rescue_date: str | None = None  # "YYYY-MM-DD"
    contact_methods: list[ContactMethod] = Field(default_factory=list)
    # 선택 슬롯
    appearance: str | None = None
    health_conditions: list[str] = Field(default_factory=list)
    personality_notes: str | None = None

    @field_validator("rescue_date")
    @classmethod
    def validate_date_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import re
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError("rescue_date는 YYYY-MM-DD 형식이어야 합니다")
        return v


REQUIRED_KEYS = [
    "breed",
    "estimated_age",
    "sex",
    "is_neutered",
    "weight_kg",
    "rescue_region",
    "rescue_date",
    "contact_methods",
]

OPTIONAL_KEYS = [
    "appearance",
    "health_conditions",
    "personality_notes",
]


class SlotValidateRequest(ApiSlots):
    pass


class SlotValidateResponse(BaseModel):
    data: ApiSlots
    missing_required: list[str]
    is_complete: bool


class SlotMetaResponse(BaseModel):
    required: list[str]
    optional: list[str]
