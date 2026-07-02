import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationSetting(Base):
    __tablename__ = "notification_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    adoption_inquiry: Mapped[bool] = mapped_column(Boolean, default=True)
    draft_reminder: Mapped[bool] = mapped_column(Boolean, default=True)
    publish_success: Mapped[bool] = mapped_column(Boolean, default=True)
    weekly_report: Mapped[bool] = mapped_column(Boolean, default=False)
    app_push: Mapped[bool] = mapped_column(Boolean, default=True)
    email_notif: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
