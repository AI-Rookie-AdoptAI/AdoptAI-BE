from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator


class AgeValue(BaseModel):
    value: int
    unit: Literal["년", "개월"]


class ApiSlots(BaseModel):
    # 필수 슬롯
    breed: str | None = None
    estimated_age: AgeValue | None = None
    sex: Literal["수컷", "암컷", "미상"] | None = None
    is_neutered: bool | None = None
    weight_kg: float | None = None
    rescue_region: str | None = None
    rescue_date: str | None = None  # "YYYY-MM-DD"
    shelter_contact: str | None = None
    # 선택 슬롯
    appearance: str | None = None
    health_conditions: list[str] = []
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
    "shelter_contact",
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
