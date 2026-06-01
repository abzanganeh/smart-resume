"""Data export and account closure models (SYSTEM_DESIGN_PHASE_2 §19.6)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExportJobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


_EXPORT_STATUS_PG = PGEnum(
    ExportJobStatus,
    name="export_job_status",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)

CLOSURE_GRACE_DAYS = 30
EXPORT_PRESIGNED_TTL_SECONDS = 24 * 3600


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ExportJobStatus] = mapped_column(
        _EXPORT_STATUS_PG,
        nullable=False,
        default=ExportJobStatus.pending,
        server_default=ExportJobStatus.pending.value,
    )
    s3_key: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    presigned_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    presigned_url_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_export_jobs_user_created", "user_id", "created_at"),
    )


class ClosureRequest(Base):
    __tablename__ = "closure_requests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    scheduled_delete_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    day23_reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_closure_requests_scheduled_delete",
            "scheduled_delete_at",
            postgresql_where=text("cancelled_at IS NULL"),
        ),
    )


__all__ = [
    "CLOSURE_GRACE_DAYS",
    "EXPORT_PRESIGNED_TTL_SECONDS",
    "ClosureRequest",
    "ExportJob",
    "ExportJobStatus",
]
