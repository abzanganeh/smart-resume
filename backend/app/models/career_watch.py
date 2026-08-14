"""Career Watch persistence models (pricing milestone slice 11).

Global company registry, per-user watch lists, polled job cache, and alert
rows consumed by the poller/matcher lambdas and ``/api/career-watch/*``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CareerAtsType(str, enum.Enum):
    unknown = "unknown"
    greenhouse = "greenhouse"
    lever = "lever"
    ashby = "ashby"
    workday = "workday"
    generic_html = "generic_html"


class CareerAlertStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    dismissed = "dismissed"
    expired = "expired"


_CAREER_ATS_TYPE_PG = PGEnum(
    CareerAtsType,
    name="career_ats_type",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
_CAREER_ALERT_STATUS_PG = PGEnum(
    CareerAlertStatus,
    name="career_alert_status",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class WatchedCompany(Base):
    """Canonical company row shared across users."""

    __tablename__ = "watched_companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    careers_page_url: Mapped[str] = mapped_column(Text, nullable=False)
    ats_type: Mapped[CareerAtsType] = mapped_column(
        _CAREER_ATS_TYPE_PG,
        nullable=False,
        default=CareerAtsType.unknown,
        server_default=CareerAtsType.unknown.value,
    )
    ats_board_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    poll_fail_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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
        Index("ix_watched_companies_active_poll", "is_active", "last_polled_at"),
    )


class UserWatchedCompany(Base):
    """Per-user watch subscription with keyword filters."""

    __tablename__ = "user_watched_companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    watched_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("watched_companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    keywords: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    last_matched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    watched_company: Mapped["WatchedCompany"] = relationship(
        "WatchedCompany", lazy="raise"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "watched_company_id", name="uq_user_watched_company"),
        Index("ix_user_watched_companies_active", "user_id", "is_active"),
    )


class CareerJobCache(Base):
    """Jobs discovered on a company's careers page."""

    __tablename__ = "career_job_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    watched_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("watched_companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    location: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default=""
    )
    apply_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    posted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    is_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        UniqueConstraint(
            "watched_company_id",
            "external_job_id",
            name="uq_career_job_cache_company_external",
        ),
        Index("ix_career_job_cache_company_open", "watched_company_id", "is_open"),
    )


class CareerAlert(Base):
    """Matched job alert for a user (pending → sent/dismissed)."""

    __tablename__ = "career_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_watched_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_watched_companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    career_job_cache_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("career_job_cache.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    match_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[CareerAlertStatus] = mapped_column(
        _CAREER_ALERT_STATUS_PG,
        nullable=False,
        default=CareerAlertStatus.pending,
        server_default=CareerAlertStatus.pending.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    notified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "career_job_cache_id", name="uq_career_alert_user_job"
        ),
        Index("ix_career_alerts_user_status", "user_id", "status"),
    )


__all__ = [
    "CareerAlert",
    "CareerAlertStatus",
    "CareerAtsType",
    "CareerJobCache",
    "UserWatchedCompany",
    "WatchedCompany",
]
