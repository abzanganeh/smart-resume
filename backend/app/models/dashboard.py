"""Dashboard persistence models (SYSTEM_DESIGN_PHASE_2 §19.3)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResumeRecordStatus(str, enum.Enum):
    draft = "draft"
    applied = "applied"
    interviewing = "interviewing"
    offer = "offer"
    rejected = "rejected"
    withdrawn = "withdrawn"


class AtsRecalcType(str, enum.Enum):
    initial = "initial"
    manual = "manual"
    auto = "auto"


_RESUME_RECORD_STATUS_PG = PGEnum(
    ResumeRecordStatus,
    name="resume_record_status",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
_ATS_RECALC_TYPE_PG = PGEnum(
    AtsRecalcType,
    name="ats_recalc_type",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class ResumeRecord(Base):
    __tablename__ = "resume_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    jd_title: Mapped[str] = mapped_column(String(500), nullable=False)
    jd_company: Mapped[str] = mapped_column(String(500), nullable=False)
    jd_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    current_ats_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    starting_ats_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[ResumeRecordStatus] = mapped_column(
        _RESUME_RECORD_STATUS_PG,
        nullable=False,
        default=ResumeRecordStatus.draft,
        server_default=ResumeRecordStatus.draft.value,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    score_history: Mapped[list["AtsScoreHistory"]] = relationship(
        back_populates="resume_record",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AtsScoreHistory.triggered_at",
    )

    __table_args__ = (
        Index("ix_resume_records_user_updated", "user_id", "updated_at"),
        Index(
            "uq_resume_records_user_jd_hash",
            "user_id",
            "jd_text_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    @property
    def ats_score_delta(self) -> int:
        return self.current_ats_score - self.starting_ats_score


class AtsScoreHistory(Base):
    __tablename__ = "ats_score_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    resume_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    recalc_type: Mapped[AtsRecalcType] = mapped_column(
        _ATS_RECALC_TYPE_PG, nullable=False
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    resume_record: Mapped["ResumeRecord"] = relationship(
        back_populates="score_history"
    )

    __table_args__ = (
        Index(
            "ix_ats_score_history_record_triggered",
            "resume_record_id",
            "triggered_at",
        ),
    )


__all__ = [
    "AtsRecalcType",
    "AtsScoreHistory",
    "ResumeRecord",
    "ResumeRecordStatus",
]
