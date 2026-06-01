"""Application tracker models (SYSTEM_DESIGN_PHASE_2 §19.4)."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApplicationStatus(str, enum.Enum):
    draft = "draft"
    applied = "applied"
    interviewing = "interviewing"
    offer = "offer"
    accepted = "accepted"
    rejected = "rejected"
    withdrawn = "withdrawn"


class InterviewFormat(str, enum.Enum):
    phone = "phone"
    video = "video"
    onsite = "onsite"
    take_home = "take_home"
    other = "other"


class InterviewOutcome(str, enum.Enum):
    pending = "pending"
    passed = "passed"
    failed = "failed"
    no_show = "no_show"


class OfferDecision(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


class RejectionReason(str, enum.Enum):
    ghosted = "ghosted"
    explicit_rejection = "explicit_rejection"
    position_filled = "position_filled"
    withdrew = "withdrew"
    other = "other"


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> PGEnum:
    return PGEnum(
        enum_cls,
        name=name,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


_APPLICATION_STATUS_PG = _pg_enum(ApplicationStatus, "application_status")
_INTERVIEW_FORMAT_PG = _pg_enum(InterviewFormat, "interview_format")
_INTERVIEW_OUTCOME_PG = _pg_enum(InterviewOutcome, "interview_outcome")
_OFFER_DECISION_PG = _pg_enum(OfferDecision, "offer_decision")
_REJECTION_REASON_PG = _pg_enum(RejectionReason, "rejection_reason")

MAX_ATTACHMENTS_PER_APPLICATION = 5
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_ATTACHMENT_TOTAL_BYTES = 25 * 1024 * 1024


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resume_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    jd_title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    jd_company: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[ApplicationStatus] = mapped_column(
        _APPLICATION_STATUS_PG,
        nullable=False,
        default=ApplicationStatus.draft,
        server_default=ApplicationStatus.draft.value,
    )
    applied_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    follow_up_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    rejection_reason: Mapped[RejectionReason | None] = mapped_column(
        _REJECTION_REASON_PG, nullable=True
    )
    rejection_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
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

    interview_rounds: Mapped[list["InterviewRound"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InterviewRound.round_number",
    )
    offer_detail: Mapped["OfferDetail | None"] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    attachments: Mapped[list["ApplicationAttachment"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ApplicationAttachment.uploaded_at",
    )

    __table_args__ = (
        Index("ix_applications_user_status", "user_id", "status"),
        Index(
            "ix_applications_resume_record_id",
            "resume_record_id",
            unique=True,
            postgresql_where=text("resume_record_id IS NOT NULL"),
        ),
    )


class InterviewRound(Base):
    __tablename__ = "interview_rounds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[InterviewFormat] = mapped_column(
        _INTERVIEW_FORMAT_PG, nullable=False
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interviewers: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[InterviewOutcome | None] = mapped_column(
        _INTERVIEW_OUTCOME_PG, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    application: Mapped["Application"] = relationship(back_populates="interview_rounds")


class OfferDetail(Base):
    __tablename__ = "offer_details"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    base_salary_usd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bonus_usd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    equity_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sign_on_usd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    benefits: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remote: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    response_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision: Mapped[OfferDecision | None] = mapped_column(
        _OFFER_DECISION_PG, nullable=True
    )
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    application: Mapped["Application"] = relationship(back_populates="offer_detail")


class ApplicationAttachment(Base):
    __tablename__ = "application_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    application: Mapped["Application"] = relationship(back_populates="attachments")


__all__ = [
    "MAX_ATTACHMENT_BYTES",
    "MAX_ATTACHMENT_TOTAL_BYTES",
    "MAX_ATTACHMENTS_PER_APPLICATION",
    "Application",
    "ApplicationAttachment",
    "ApplicationStatus",
    "InterviewFormat",
    "InterviewOutcome",
    "InterviewRound",
    "OfferDecision",
    "OfferDetail",
    "RejectionReason",
]
