from datetime import datetime

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    profile_image_url: str | None = None
    created_at: datetime


class UpdateUserRequest(BaseModel):
    name: str | None = None
    current_password: str | None = None
    new_password: str | None = Field(None, min_length=8)


class NotificationSettingResponse(BaseModel):
    adoption_inquiry: bool
    draft_reminder: bool
    publish_success: bool
    weekly_report: bool
    app_push: bool
    email_notif: bool


class UpdateNotificationSettingRequest(BaseModel):
    adoption_inquiry: bool | None = None
    draft_reminder: bool | None = None
    publish_success: bool | None = None
    weekly_report: bool | None = None
    app_push: bool | None = None
    email_notif: bool | None = None
