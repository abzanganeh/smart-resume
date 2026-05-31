"""SQLAlchemy ORM models for the master resume (profile document).

Mirrors the schemas defined in ``docs/SYSTEM_DESIGN_PHASE_2.md`` §18.4 and the
retrieval contract in ``docs/IMPLEMENTATION_PLAN.md`` §6a.

Storage:

- :class:`MasterResume` — one row per user holding the last raw upload,
  the structured ``parsed_sections``, and bookkeeping (``chunk_count``,
  ``last_embedded_at``).
- :class:`MasterResumeChunk` — one row per logical "available content"
  unit (one bullet, one project header, one skill cluster, …).  Each
  carries the chunk text, a ``tiktoken`` token count for budget
  accounting, and a 1536-dim ``pgvector`` embedding produced by
  ``text-embedding-3-small``.

The Postgres-side DDL (extension, enums, table, index) lives in
``alembic/versions/0003_master_resume.py``.  The Python enums use
``create_type=False`` so the migration is the only place the type is
created or dropped — matches the convention used by ``user.py`` /
``billing.py``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# Embedding model dimensionality.  ``text-embedding-3-small`` outputs
# 1536-dim float vectors.  Kept here (and asserted in the migration) so
# any future change to ``RETRIEVAL_EMBEDDING_MODEL`` is forced through a
# migration rather than silently breaking ANN queries.
EMBEDDING_DIM = 1536


class MasterResumeSectionType(str, enum.Enum):
    """Section labels carried on every chunk row.

    Matches the canonical list in SYSTEM_DESIGN_PHASE_2 §18.4 storage
    block.  The names also drive retrieval per-section caps in
    ``services/retrieval/config.py``.
    """

    summary = "summary"
    experience = "experience"
    skills = "skills"
    education = "education"
    project = "project"
    cert = "cert"
    publication = "publication"
    award = "award"
    volunteer = "volunteer"
    language = "language"
    patent = "patent"
    other = "other"


MASTER_RESUME_SECTION_ENUM_NAME = "master_resume_section_type"

_SECTION_TYPE_PG = PGEnum(
    MasterResumeSectionType,
    name=MASTER_RESUME_SECTION_ENUM_NAME,
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# MasterResume
# ---------------------------------------------------------------------------


class MasterResume(Base):
    """Per-user profile document.

    ``user_id`` is unique — SYSTEM_DESIGN_PHASE_2 §18.4 explicitly states
    "one master resume per user".  Re-upload replaces the row; the
    chunks are wiped + re-embedded by the service layer.
    """

    __tablename__ = "master_resumes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parsed_sections: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_embedded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Hirebase resume-matching artifact (POST /v2/resumes/embed).
    hirebase_artifact_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
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

    chunks: Mapped[list["MasterResumeChunk"]] = relationship(
        back_populates="master_resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


# ---------------------------------------------------------------------------
# MasterResumeChunk
# ---------------------------------------------------------------------------


class MasterResumeChunk(Base):
    """One logical bullet / paragraph / skill cluster of the master resume.

    Schema mirrors SYSTEM_DESIGN_PHASE_2 §18.4 verbatim.  ``deleted_at``
    is a soft-delete tombstone — the retrieval query and the ``GET
    /api/profile/resume/chunks`` endpoint always filter ``deleted_at IS
    NULL``.  Soft-delete keeps version-snapshot transparency intact for
    older tailored resumes that referenced now-removed chunks.
    """

    __tablename__ = "master_resume_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    master_resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("master_resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalized user_id so ANN queries can filter by user without a
    # join.  Kept FK-consistent via ``ON DELETE CASCADE`` in the migration.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_type: Mapped[MasterResumeSectionType] = mapped_column(
        _SECTION_TYPE_PG, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # ``embedding`` is nullable so a chunk row can be inserted before the
    # embedding API call returns — the service layer fills it in within
    # the same transaction.  ANN queries always filter ``embedding IS
    # NOT NULL``.
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
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

    master_resume: Mapped["MasterResume"] = relationship(back_populates="chunks")

    __table_args__ = (
        Index(
            "ix_master_resume_chunks_user_section_live",
            "user_id",
            "section_type",
            # Filter live rows at index level so the ANN query can use a
            # narrow scan.  Soft-deleted rows are kept for version replay
            # but should never enter retrieval.
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_master_resume_chunks_master_resume_id_created",
            "master_resume_id",
            "created_at",
        ),
    )


__all__ = [
    "EMBEDDING_DIM",
    "MASTER_RESUME_SECTION_ENUM_NAME",
    "MasterResume",
    "MasterResumeChunk",
    "MasterResumeSectionType",
]
