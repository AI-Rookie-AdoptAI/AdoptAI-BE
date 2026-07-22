from fastapi import APIRouter

from app.schemas.slots import (
    OPTIONAL_KEYS,
    REQUIRED_KEYS,
    AgeValue,
    ApiSlots,
    ContactMethod,
    SlotMetaResponse,
    SlotValidateRequest,
    SlotValidateResponse,
)

router = APIRouter(prefix="/slots", tags=["Slots"])

_SLOT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "AdoptionSlots",
    "type": "object",
    "properties": {
        "breed": {"type": "string", "description": "품종"},
        "estimated_age": {
            "type": "object",
            "properties": {
                "value": {"type": "number"},
                "unit": {"type": "string", "enum": ["년", "개월", "일"]},
            },
            "required": ["value", "unit"],
            "description": "추정 나이",
        },
        "sex": {"type": "string", "enum": ["수컷", "암컷", "미상"], "description": "성별"},
        "is_neutered": {"type": ["boolean", "null"], "description": "중성화 여부"},
        "weight_kg": {"type": "number", "description": "체중 (kg)"},
        "rescue_region": {"type": "string", "description": "구조 지역"},
        "rescue_date": {"type": "string", "format": "date", "description": "구조 일자 (YYYY-MM-DD)"},
        "contact_methods": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"enum": ["phone", "instagram", "kakao", "other"]},
                    "value": {"type": "string"},
                },
                "required": ["type", "value"],
            },
        },
        "appearance": {"type": "string", "description": "모색/외형 특징"},
        "health_conditions": {"type": "array", "items": {"type": "string"}, "description": "건강 상태"},
        "personality_notes": {"type": "string", "description": "성격/특이사항"},
    },
    "required": REQUIRED_KEYS,
}

_EXAMPLE = ApiSlots(
    breed="말티즈",
    estimated_age=AgeValue(value=2, unit="년"),
    sex="수컷",
    is_neutered=True,
    weight_kg=3.0,
    rescue_region="제주시 일도이동",
    rescue_date="2026-06-30",
    contact_methods=[ContactMethod(type="phone", value="064-710-4805")],
    appearance="흰색 장모",
    health_conditions=["심장사상충 음성"],
    personality_notes="사람을 잘 따름",
)


@router.get("/schema", summary="슬롯 JSON Schema 반환")
async def get_schema() -> dict:
    return _SLOT_SCHEMA


@router.get("/meta", response_model=SlotMetaResponse, summary="required/optional 슬롯 목록")
async def get_meta() -> SlotMetaResponse:
    return SlotMetaResponse(required=REQUIRED_KEYS, optional=OPTIONAL_KEYS)


@router.post("/validate", response_model=SlotValidateResponse, summary="LLM 추출 결과 검증·정규화")
async def validate_slots(body: SlotValidateRequest) -> SlotValidateResponse:
    data = ApiSlots.model_validate(body.model_dump())
    missing = [
        key
        for key in REQUIRED_KEYS
        if getattr(data, key) is None or (key == "contact_methods" and not data.contact_methods)
    ]
    return SlotValidateResponse(
        data=data,
        missing_required=missing,
        is_complete=len(missing) == 0,
    )


@router.get("/example", response_model=ApiSlots, summary="예시 슬롯 반환")
async def get_example() -> ApiSlots:
    return _EXAMPLE
