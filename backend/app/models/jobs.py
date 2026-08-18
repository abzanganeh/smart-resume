"""Job search persistence models (SYSTEM_DESIGN_PHASE_2 §18.10)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobSearchSource(str, enum.Enum):
    cache = "cache"
    hirebase = "hirebase"
    apify = "apify"


class AlertFrequency(str, enum.Enum):
    off = "off"
    daily = "daily"
    weekly = "weekly"


_JOB_SEARCH_SOURCE_PG = PGEnum(
    JobSearchSource,
    name="job_search_source",
    create_type=False,
)
_ALERT_FREQUENCY_PG = PGEnum(
    AlertFrequency,
    name="alert_frequency",
    create_type=False,
)


class JobCache(Base):
    __tablename__ = "job_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sources: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    external_ids: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(500), nullable=False)
    company_normalized: Mapped[str] = mapped_column(String(500), nullable=False)
    location: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    location_city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location_country: Mapped[str | None] = mapped_column(String(200), nullable=True)
    remote: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    salary_min_usd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max_usd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency_original: Mapped[str | None] = mapped_column(String(10), nullable=True)
    employment_type: Mapped[str] = mapped_column(
        String(80), nullable=False, default="", server_default=""
    )
    posted_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    apply_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    cached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    dedup_key: Mapped[str] = mapped_column(String(512), nullable=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    apply_url_normalized: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    ats_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_job_cache_company_normalized", "company_normalized"),
        Index("uq_job_cache_dedup_key", "dedup_key", unique=True),
        Index(
            "ix_job_cache_expires_at_cleanup",
            "expires_at",
            postgresql_where=text("expires_at IS NOT NULL"),
        ),
        Index("ix_job_cache_active_first_seen", "is_active", "first_seen_at"),
    )


class JobSearchLog(Base):
    __tablename__ = "job_search_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[JobSearchSource] = mapped_column(
        _JOB_SEARCH_SOURCE_PG, nullable=False
    )
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_job_search_log_created_at", "created_at"),
        Index("ix_job_search_log_query_created", "query", "created_at"),
    )


class SavedJob(Base):
    """User bookmark for a cached job listing."""

    __tablename__ = "saved_job"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_cache_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_cache.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("uq_saved_job_user_job", "user_id", "job_cache_id", unique=True),
    )


class SavedSearch(Base):
    __tablename__ = "saved_search"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    alert_frequency: Mapped[AlertFrequency] = mapped_column(
        _ALERT_FREQUENCY_PG,
        nullable=False,
        default=AlertFrequency.off,
        server_default=AlertFrequency.off.value,
    )
    last_alerted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    __table_args__ = (Index("ix_saved_search_alert_frequency", "alert_frequency"),)


__all__ = [
    "AlertFrequency",
    "JobCache",
    "JobSearchLog",
    "JobSearchSource",
    "SavedJob",
    "SavedSearch",
]
