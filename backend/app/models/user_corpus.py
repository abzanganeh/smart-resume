"""ORM model for the multi-source RAG corpus.

Every user builds up a personal corpus over time:
  master_resume    — chunks from the structured master resume (sourced
                     from master_resume_chunks for unified retrieval)
  tailored_resume  — bullets / summary produced by Phase 3 after each run
  bullet_fix       — individual bullets accepted from Phase 2 audit suggestions
  user_note        — free-form notes the user types in the context panel
  claimed_keyword  — single-term claims the user adds during context review

All sources share the same 1536-dim text-embedding-3-small vector space as
``master_resume_chunks`` so a single ANN query can retrieve across tables
using UNION ALL.
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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.master_resume import EMBEDDING_DIM

CORPUS_SOURCE_ENUM_NAME = "corpus_source"


class CorpusSource(str, enum.Enum):
    master_resume = "master_resume"
    tailored_resume = "tailored_resume"
    bullet_fix = "bullet_fix"
    user_note = "user_note"
    claimed_keyword = "claimed_keyword"


_CORPUS_SOURCE_PG = PGEnum(
    CorpusSource,
    name=CORPUS_SOURCE_ENUM_NAME,
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserCorpusChunk(Base):
    """One embedded text fragment from any user corpus source.

    Soft-delete via ``deleted_at`` mirrors the master_resume_chunks
    contract so retrieval queries stay consistent across both tables.
    """

    __tablename__ = "user_corpus_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Nullable — notes and keywords have no session context.
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    corpus_source: Mapped[CorpusSource] = mapped_column(
        _CORPUS_SOURCE_PG, nullable=False
    )
    # Mirror of master_resume_chunks.section_type — stored as plain text
    # to avoid coupling to the master_resume_section_type PG enum.
    section_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )
    # Provenance JSON: bullet_index, company, jd_hash, etc.
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_user_corpus_chunks_user_source_live",
            "user_id",
            "corpus_source",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_user_corpus_chunks_session",
            "session_id",
            postgresql_where=text("session_id IS NOT NULL"),
        ),
    )


__all__ = ["CorpusSource", "CORPUS_SOURCE_ENUM_NAME", "UserCorpusChunk"]
