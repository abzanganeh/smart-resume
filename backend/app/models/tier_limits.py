"""Admin-configurable subscription tier limits.

Replaces hard-coded ``PLAN_RESUMES_PER_PERIOD`` / ``PLAN_SEARCHES_PER_PERIOD``
in ``quota.py``.  One active row per ``plan_code`` at a time; admin updates
deactivate the prior row and insert a new one (same pattern as ``PlanConfig``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TierLimitsConfig(Base):
    __tablename__ = "tier_limits_config"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    resumes_per_period: Mapped[int] = mapped_column(Integer, nullable=False)
    cover_letters_per_period: Mapped[int] = mapped_column(Integer, nullable=False)
    searches_per_period: Mapped[int] = mapped_column(Integer, nullable=False)
    fit_analyses_per_period: Mapped[int] = mapped_column(Integer, nullable=False)
    checkups_per_period: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    story_sessions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    coached_sessions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    career_watch_companies: Mapped[int] = mapped_column(Integer, nullable=False)
    career_watch_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    tracker_active_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    whisper_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    whisper_uses_per_period: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    llm_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    llm_model_phase3: Mapped[str] = mapped_column(String(255), nullable=False)

    soft_cap_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    updated_by_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
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
        Index("ix_tier_limits_config_plan_active", "plan_code", "is_active"),
    )


__all__ = ["TierLimitsConfig"]
