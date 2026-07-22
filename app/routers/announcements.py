from copy import deepcopy
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.announcement import Announcement
from app.models.chat import ChatSession, Message
from app.models.user import User
from app.schemas.announcement import (
    AnnouncementListResponse,
    AnnouncementPetInfo,
    AnnouncementStatus,
    AnnouncementUpdate,
    ApiAnnouncement,
    ApiDraftInAnnouncement,
    PlatformVariant,
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
        platform_variants=(ann.draft or {}).get("platform_variants", {}),
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


@router.patch("/{announcement_id}", response_model=ApiAnnouncement, summary="공고 수정")
async def update_announcement(
    announcement_id: str,
    body: AnnouncementUpdate,
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
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")

    changes = body.model_dump(exclude_unset=True, mode="json")
    if "description" in changes and changes["description"] is None:
        changes["description"] = ""
    if changes.get("pet_info") is None:
        changes.pop("pet_info", None)
    for field in ("title", "description", "pet_info"):
        if field in changes and not (field == "title" and changes[field] is None):
            setattr(ann, field, changes[field])
    if ann.draft:
        draft = deepcopy(ann.draft)
        if changes.get("title") is not None:
            draft["title"] = changes["title"]
            for variant in (draft.get("platform_variants") or {}).values():
                if isinstance(variant, dict):
                    variant["title"] = changes["title"]
        if "description" in changes:
            draft["description"] = changes["description"]
        if "pet_info" in changes:
            draft["pet_info"] = changes["pet_info"]
        ann.draft = draft
    ann.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(ann)
    return _to_response(ann, include_draft=True)


@router.patch(
    "/{announcement_id}/platform-variants/{platform}",
    response_model=PlatformVariant,
    summary="플랫폼별 공고 수정본 저장",
)
async def update_platform_variant(
    announcement_id: str,
    platform: str,
    body: PlatformVariant,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlatformVariant:
    if platform not in {"instagram", "daangn", "naver_cafe"} or body.platform != platform:
        raise HTTPException(status_code=400, detail="플랫폼 값이 일치하지 않습니다")
    result = await db.execute(
        select(Announcement).where(
            Announcement.id == announcement_id,
            Announcement.user_id == current_user.id,
        )
    )
    ann = result.scalar_one_or_none()
    if not ann or not ann.draft:
        raise HTTPException(status_code=404, detail="수정할 공고 초안을 찾을 수 없습니다")

    draft = deepcopy(ann.draft)
    variants = dict(draft.get("platform_variants") or {})
    variants[platform] = body.model_dump(mode="json")
    draft["platform_variants"] = variants
    ann.draft = draft
    if ann.status == "draft":
        ann.status = "in_review"
    ann.updated_at = datetime.now(UTC)
    await db.commit()
    return body


@router.post(
    "/{announcement_id}/duplicate",
    response_model=ApiAnnouncement,
    status_code=status.HTTP_201_CREATED,
    summary="공고 복제",
)
async def duplicate_announcement(
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
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")

    cloned_draft = deepcopy(source.draft)
    has_platform_files = bool((cloned_draft or {}).get("platform_variants"))
    clone = Announcement(
        user_id=current_user.id,
        status="in_review" if has_platform_files else "draft",
        title=f"{source.title or '입양 공고'} (복사본)",
        description=source.description,
        pet_info=deepcopy(source.pet_info),
        photos=deepcopy(source.photos or []),
        draft=cloned_draft,
    )
    if clone.draft:
        clone.draft["title"] = clone.title
    db.add(clone)
    await db.commit()
    await db.refresh(clone)
    return _to_response(clone, include_draft=True)


@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT, summary="공고 삭제")
async def delete_announcement(
    announcement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    result = await db.execute(
        select(Announcement).where(
            Announcement.id == announcement_id,
            Announcement.user_id == current_user.id,
        )
    )
    ann = result.scalar_one_or_none()
    if not ann:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")

    sessions = await db.execute(select(ChatSession.id).where(ChatSession.announcement_id == ann.id))
    session_ids = list(sessions.scalars().all())
    if session_ids:
        await db.execute(delete(Message).where(Message.session_id.in_(session_ids)))
        await db.execute(delete(ChatSession).where(ChatSession.id.in_(session_ids)))
    await db.delete(ann)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
