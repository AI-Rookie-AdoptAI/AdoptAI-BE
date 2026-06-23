from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.announcement import Announcement
from app.models.user import User
from app.schemas.announcement import (
    AnnouncementDetailResponse,
    AnnouncementListResponse,
    AnnouncementResponse,
    AnnouncementStatus,
    AnnouncementUpdate,
    PetInfo,
    PublishResponse,
)

router = APIRouter(prefix="/announcements", tags=["Announcements"])


def _to_response(ann: Announcement) -> AnnouncementResponse:
    return AnnouncementResponse(
        id=ann.id,
        status=AnnouncementStatus(ann.status),
        pet_info=PetInfo(**ann.pet_info) if ann.pet_info else None,
        photos=ann.photos or [],
        description=ann.description,
        created_at=ann.created_at,
        updated_at=ann.updated_at,
    )


def _to_detail_response(ann: Announcement) -> AnnouncementDetailResponse:
    return AnnouncementDetailResponse(
        id=ann.id,
        status=AnnouncementStatus(ann.status),
        pet_info=PetInfo(**ann.pet_info) if ann.pet_info else None,
        photos=ann.photos or [],
        description=ann.description,
        chat_session_id=ann.chat_session_id,
        created_at=ann.created_at,
        updated_at=ann.updated_at,
    )


@router.get(
    "",
    response_model=AnnouncementListResponse,
    summary="공고 목록 조회",
    description="현재 사용자의 공고 목록을 페이지네이션으로 조회합니다.",
)
async def list_announcements(
    status: AnnouncementStatus | None = Query(None, description="공고 상태 필터"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnnouncementListResponse:
    query = select(Announcement).where(Announcement.user_id == current_user.id)
    if status:
        query = query.where(Announcement.status == status.value)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    query = query.order_by(Announcement.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    items = [_to_response(a) for a in result.scalars().all()]

    return AnnouncementListResponse(items=items, total=total, page=page, size=size)


@router.post(
    "",
    response_model=AnnouncementDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="공고 생성",
    description="빈 초안 공고를 생성합니다. 이후 채팅 세션과 연결됩니다.",
)
async def create_announcement(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnnouncementDetailResponse:
    ann = Announcement(user_id=current_user.id)
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    return _to_detail_response(ann)


@router.get(
    "/{announcement_id}",
    response_model=AnnouncementDetailResponse,
    summary="공고 상세 조회",
)
async def get_announcement(
    announcement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnnouncementDetailResponse:
    result = await db.execute(
        select(Announcement).where(
            Announcement.id == announcement_id,
            Announcement.user_id == current_user.id,
        )
    )
    ann = result.scalar_one_or_none()
    if not ann:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="공고를 찾을 수 없습니다")
    return _to_detail_response(ann)


@router.patch(
    "/{announcement_id}",
    response_model=AnnouncementDetailResponse,
    summary="공고 수정",
    description="pet_info 및 description을 업데이트합니다. 포함된 필드만 변경됩니다.",
)
async def update_announcement(
    announcement_id: str,
    body: AnnouncementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnnouncementDetailResponse:
    result = await db.execute(
        select(Announcement).where(
            Announcement.id == announcement_id,
            Announcement.user_id == current_user.id,
        )
    )
    ann = result.scalar_one_or_none()
    if not ann:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="공고를 찾을 수 없습니다")

    if body.pet_info is not None:
        ann.pet_info = body.pet_info.model_dump()
    if body.description is not None:
        ann.description = body.description

    ann.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ann)
    return _to_detail_response(ann)


@router.post(
    "/{announcement_id}/publish",
    response_model=PublishResponse,
    summary="공고 게시 요청",
    description="공고를 검토 대기(in_review) 상태로 전환합니다.",
)
async def publish_announcement(
    announcement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PublishResponse:
    result = await db.execute(
        select(Announcement).where(
            Announcement.id == announcement_id,
            Announcement.user_id == current_user.id,
        )
    )
    ann = result.scalar_one_or_none()
    if not ann:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="공고를 찾을 수 없습니다")
    if ann.status != AnnouncementStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"초안 상태의 공고만 게시 요청할 수 있습니다 (현재: {ann.status})",
        )

    ann.status = AnnouncementStatus.IN_REVIEW
    ann.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ann)
    return PublishResponse(id=ann.id, status=AnnouncementStatus(ann.status), updated_at=ann.updated_at)
