from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.shelter import Shelter
from app.models.user import User
from app.schemas.shelter import ShelterResponse, UpdateShelterRequest

router = APIRouter(prefix="/shelters", tags=["Shelters"])


def _to_response(s: Shelter) -> ShelterResponse:
    return ShelterResponse(
        id=s.id,
        name=s.name,
        region=s.region,
        address=s.address,
        phone=s.phone,
        email=s.email,
        capacity=s.capacity,
        description=s.description,
    )


@router.get("/me", response_model=ShelterResponse, summary="내 보호소 정보 조회")
async def get_my_shelter(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ShelterResponse:
    result = await db.execute(select(Shelter).where(Shelter.user_id == current_user.id))
    shelter = result.scalar_one_or_none()
    if not shelter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="보호소 정보가 없습니다. 먼저 등록해 주세요.")
    return _to_response(shelter)


@router.patch("/me", response_model=ShelterResponse, summary="보호소 정보 등록/수정")
async def upsert_my_shelter(
    body: UpdateShelterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ShelterResponse:
    result = await db.execute(select(Shelter).where(Shelter.user_id == current_user.id))
    shelter = result.scalar_one_or_none()

    if not shelter:
        shelter = Shelter(user_id=current_user.id)
        db.add(shelter)

    shelter.name = body.name
    shelter.region = body.region
    shelter.phone = body.phone
    shelter.address = body.address
    shelter.email = body.email
    shelter.capacity = body.capacity
    shelter.description = body.description
    shelter.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(shelter)
    return _to_response(shelter)
