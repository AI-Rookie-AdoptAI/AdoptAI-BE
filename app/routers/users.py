from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.dependencies import get_current_user
from app.models.notification_setting import NotificationSetting
from app.models.user import User
from app.schemas.user import (
    NotificationSettingResponse,
    UpdateNotificationSettingRequest,
    UpdateUserRequest,
    UserResponse,
)

router = APIRouter(prefix="/users", tags=["Users"])


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        profile_image_url=None,
        created_at=user.created_at,
    )


@router.patch("/me", response_model=UserResponse, summary="프로필 수정")
async def update_me(
    body: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    if body.new_password:
        if not body.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="비밀번호 변경 시 current_password가 필요합니다",
            )
        if not verify_password(body.current_password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="현재 비밀번호가 올바르지 않아요",
            )
        current_user.hashed_password = hash_password(body.new_password)

    if body.name is not None:
        current_user.name = body.name

    await db.commit()
    await db.refresh(current_user)
    return _to_user_response(current_user)


async def _get_or_create_notification_setting(
    user_id: str, db: AsyncSession
) -> NotificationSetting:
    result = await db.execute(
        select(NotificationSetting).where(NotificationSetting.user_id == user_id)
    )
    setting = result.scalar_one_or_none()
    if not setting:
        setting = NotificationSetting(user_id=user_id)
        db.add(setting)
        await db.flush()
    return setting


def _to_notif_response(s: NotificationSetting) -> NotificationSettingResponse:
    return NotificationSettingResponse(
        adoption_inquiry=s.adoption_inquiry,
        draft_reminder=s.draft_reminder,
        publish_success=s.publish_success,
        weekly_report=s.weekly_report,
        app_push=s.app_push,
        email_notif=s.email_notif,
    )


@router.get(
    "/me/notification-settings",
    response_model=NotificationSettingResponse,
    summary="알림 설정 조회",
)
async def get_notification_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationSettingResponse:
    setting = await _get_or_create_notification_setting(current_user.id, db)
    await db.commit()
    return _to_notif_response(setting)


@router.patch(
    "/me/notification-settings",
    response_model=NotificationSettingResponse,
    summary="알림 설정 수정 (partial update)",
)
async def update_notification_settings(
    body: UpdateNotificationSettingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationSettingResponse:
    setting = await _get_or_create_notification_setting(current_user.id, db)

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(setting, field, value)

    setting.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(setting)
    return _to_notif_response(setting)
