"""SQLAlchemy ORM model for extension-saved job descriptions (Strategy B Phase 2)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    company: Mapped[str | None] = mapped_column(String(512), nullable=True)
    text: Mapped[str] = mapped_column(Text(), nullable=False)
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="extension"
    )
    # Redis session_id linked when the user completes the JD wizard step.
    # Null means no session has been started for this JD yet.
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=sa_text("now()"),
    )

    __table_args__ = (
        Index("ix_job_descriptions_user_id", "user_id"),
        Index("ix_job_descriptions_user_created", "user_id", "created_at"),
    )
