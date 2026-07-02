from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.announcement import Announcement
from app.models.user import User
from app.schemas.announcement import (
    AnnouncementListResponse,
    AnnouncementPetInfo,
    AnnouncementStatus,
    AnnouncementUpdate,
    ApiAnnouncement,
    ApiDraftInAnnouncement,
    PublishAnnouncementResponse,
)

router = APIRouter(prefix="/announcements", tags=["Announcements"])


def _to_response(ann: Announcement, include_draft: bool = False) -> ApiAnnouncement:
    return ApiAnnouncement(
        id=ann.id,
        status=AnnouncementStatus(ann.status),
        title=ann.title,
        description=ann.description,
        photos=ann.photos or [],
        platform_id=ann.platform_id,
        session_id=ann.chat_session_id if ann.status == "draft" else None,
        created_at=ann.created_at,
        updated_at=ann.updated_at,
        pet_info=AnnouncementPetInfo(**ann.pet_info) if ann.pet_info else None,
        draft=ApiDraftInAnnouncement(**ann.draft) if (include_draft and ann.draft) else None,
    )


@router.get("", response_model=AnnouncementListResponse, summary="내 공고 목록")
async def list_announcements(
    status: AnnouncementStatus | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnnouncementListResponse:
    query = select(Announcement).where(Announcement.user_id == current_user.id)
    if status:
        query = query.where(Announcement.status == status.value)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    query = query.order_by(Announcement.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = [_to_response(a) for a in result.scalars().all()]

    return AnnouncementListResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/{announcement_id}", response_model=ApiAnnouncement, summary="공고 상세")
async def get_announcement(
    announcement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiAnnouncement:
    result = await db.execute(
        select(Announcement).where(
            Announcement.id == announcement_id,
            Announcement.user_id == current_user.id,
        )
    )
    ann = result.scalar_one_or_none()
    if not ann:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="공고를 찾을 수 없습니다")
    return _to_response(ann, include_draft=True)
