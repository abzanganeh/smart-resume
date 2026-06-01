"""Notification platform models (SYSTEM_DESIGN_PHASE_2 §19.5)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _pg_enum(py_enum: type[enum.Enum], name: str) -> PGEnum:
    return PGEnum(
        py_enum,
        name=name,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


class NotificationChannel(str, enum.Enum):
    in_app = "in_app"
    email = "email"
    web_push = "web_push"
    sms = "sms"
    multi = "multi"


class NotificationDeliveryStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    delivered = "delivered"
    bounced = "bounced"
    failed = "failed"


class DigestMode(str, enum.Enum):
    off = "off"
    daily = "daily"


_CHANNEL_PG = _pg_enum(NotificationChannel, "notification_channel")
_DELIVERY_PG = _pg_enum(NotificationDeliveryStatus, "notification_delivery_status")
_DIGEST_PG = _pg_enum(DigestMode, "notification_digest_mode")

# Default categories enabled per channel (§19.5).
DEFAULT_EMAIL_CATEGORIES = [
    "account_security",
    "payment",
    "subscription",
    "application_follow_up",
    "application_interview",
    "application_offer",
    "job_alerts",
    "data_export",
    "account_closure",
]
DEFAULT_IN_APP_CATEGORIES = [
    "account_security",
    "payment",
    "subscription",
    "resume",
    "application_follow_up",
    "application_interview",
    "application_nudge",
    "application_offer",
    "data_export",
    "admin_announcement",
]


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(
        String(64), nullable=False, default="general", server_default="general"
    )
    channel: Mapped[NotificationChannel] = mapped_column(_CHANNEL_PG, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_status: Mapped[NotificationDeliveryStatus] = mapped_column(
        _DELIVERY_PG,
        nullable=False,
        default=NotificationDeliveryStatus.pending,
        server_default=NotificationDeliveryStatus.pending.value,
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    # Backward-compat aliases used by tracker / billing code paths.
    @property
    def payload(self) -> dict:
        return self.data

    @payload.setter
    def payload(self, value: dict) -> None:
        self.data = value

    @property
    def status(self) -> NotificationDeliveryStatus:
        return self.delivery_status

    @status.setter
    def status(self, value: NotificationDeliveryStatus) -> None:
        self.delivery_status = value


# Legacy alias for imports that used NotificationStatus.
NotificationStatus = NotificationDeliveryStatus


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    email_enabled_categories: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    in_app_enabled_categories: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    web_push_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    sms_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    sms_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    sms_phone_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    digest_mode: Mapped[DigestMode] = mapped_column(
        _DIGEST_PG,
        nullable=False,
        default=DigestMode.off,
        server_default=DigestMode.off.value,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )


class WebPushSubscription(Base):
    __tablename__ = "web_push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    expiration_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    keys: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    user_agent: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", server_default=""
    )
    platform_hint: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "endpoint", name="uq_web_push_user_endpoint"),
    )


__all__ = [
    "DEFAULT_EMAIL_CATEGORIES",
    "DEFAULT_IN_APP_CATEGORIES",
    "DigestMode",
    "Notification",
    "NotificationChannel",
    "NotificationDeliveryStatus",
    "NotificationPreference",
    "NotificationStatus",
    "WebPushSubscription",
]
