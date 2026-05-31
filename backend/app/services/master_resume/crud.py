"""DB operations for ``master_resumes`` + ``master_resume_chunks``.

Routers in ``backend/app/routers/profile.py`` and the retrieval service
both call into this module so that the underlying ORM never leaks into
the HTTP layer.  All functions are async — the project uses
SQLAlchemy 2.0 async sessions throughout.

Soft-delete contract:

- ``delete_chunk`` sets ``deleted_at = now()`` but never removes the
  row.  Older tailored resumes may still reference the chunk via
  ``selected_chunks`` traces — keeping the row preserves audit trail.
- ``get_chunks_for_user`` always filters ``deleted_at IS NULL`` so
  retrieval never re-surfaces a hidden chunk.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_resume import (
    MasterResume,
    MasterResumeChunk,
    MasterResumeSectionType,
)
from app.services.master_resume.chunking import (
    Chunk,
    chunk_parsed_sections,
    chunk_raw_text,
    count_tokens,
)
from app.services.master_resume.embedding import embed_texts

log = structlog.get_logger("master_resume.crud")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# MasterResume row helpers
# ---------------------------------------------------------------------------


async def get_raw_resume(
    db: AsyncSession, *, user_id: uuid.UUID
) -> MasterResume | None:
    """Return the user's master resume row (or ``None`` if not uploaded)."""
    return (
        await db.execute(
            select(MasterResume).where(MasterResume.user_id == user_id)
        )
    ).scalar_one_or_none()


async def _upsert_master_resume(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    raw_text: str,
    parsed_sections: dict[str, Any],
) -> MasterResume:
    """Insert or replace the user's ``MasterResume`` row.

    Replacement is done by mutating the existing row in-place so the FK
    cascade (chunks → master_resumes) does not blow away history before
    the new chunks have been written.  Caller is responsible for the
    chunk lifecycle (wipe + recreate vs. patch).
    """
    row = await get_raw_resume(db, user_id=user_id)
    now = _utcnow()
    if row is None:
        row = MasterResume(
            id=uuid.uuid4(),
            user_id=user_id,
            raw_text=raw_text,
            parsed_sections=parsed_sections or {},
            chunk_count=0,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        await db.flush()
        return row

    row.raw_text = raw_text
    row.parsed_sections = parsed_sections or {}
    row.updated_at = now
    await db.flush()
    return row


# ---------------------------------------------------------------------------
# Chunk listing
# ---------------------------------------------------------------------------


async def get_chunks_for_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    include_deleted: bool = False,
    section_type: MasterResumeSectionType | None = None,
) -> list[MasterResumeChunk]:
    """Return all live chunks for ``user_id`` ordered for determinism.

    Ordering ``(created_at ASC, id ASC)`` matches the tie-breaker used
    by the retrieval ANN query so the order seen by ``GET
    /api/profile/resume/chunks`` is consistent with the order seen by
    the retrieval trace.
    """
    stmt = select(MasterResumeChunk).where(MasterResumeChunk.user_id == user_id)
    if not include_deleted:
        stmt = stmt.where(MasterResumeChunk.deleted_at.is_(None))
    if section_type is not None:
        stmt = stmt.where(MasterResumeChunk.section_type == section_type)
    stmt = stmt.order_by(
        MasterResumeChunk.created_at.asc(),
        MasterResumeChunk.id.asc(),
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def get_chunk(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    chunk_id: uuid.UUID,
    include_deleted: bool = False,
) -> MasterResumeChunk | None:
    stmt = select(MasterResumeChunk).where(
        MasterResumeChunk.id == chunk_id,
        MasterResumeChunk.user_id == user_id,
    )
    if not include_deleted:
        stmt = stmt.where(MasterResumeChunk.deleted_at.is_(None))
    return (await db.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Chunk write paths (create / update / delete)
# ---------------------------------------------------------------------------


async def replace_all_chunks(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    raw_text: str,
    parsed_sections: dict[str, Any] | None,
) -> tuple[MasterResume, list[MasterResumeChunk]]:
    """Full-replace flow used by POST /resume and PUT /resume.

    1. Upsert the ``master_resumes`` row.
    2. Soft-delete every existing chunk for the user.
    3. Re-chunk + embed the new payload.
    4. Insert one row per chunk inside the same transaction.

    Returns ``(master_resume, new_chunks)``.
    """
    if parsed_sections:
        chunks = chunk_parsed_sections(parsed_sections)
    else:
        chunks = chunk_raw_text(raw_text)

    resume = await _upsert_master_resume(
        db,
        user_id=user_id,
        raw_text=raw_text,
        parsed_sections=parsed_sections or {},
    )

    # Soft-delete prior chunks so they no longer participate in
    # retrieval but stay queryable for historical references.
    await db.execute(
        update(MasterResumeChunk)
        .where(
            MasterResumeChunk.user_id == user_id,
            MasterResumeChunk.deleted_at.is_(None),
        )
        .values(deleted_at=_utcnow())
    )
    await db.flush()

    rows = await _insert_chunks(db, resume=resume, user_id=user_id, chunks=chunks)
    resume.chunk_count = len(rows)
    resume.last_embedded_at = _utcnow()
    await db.flush()
    return resume, rows


async def _insert_chunks(
    db: AsyncSession,
    *,
    resume: MasterResume,
    user_id: uuid.UUID,
    chunks: Sequence[Chunk],
) -> list[MasterResumeChunk]:
    """Embed and insert ``chunks``; returns the inserted ORM rows."""
    if not chunks:
        return []

    vectors = await embed_texts([c.content for c in chunks])
    now = _utcnow()
    rows: list[MasterResumeChunk] = []
    for chunk, vector in zip(chunks, vectors):
        row = MasterResumeChunk(
            id=uuid.uuid4(),
            master_resume_id=resume.id,
            user_id=user_id,
            section_type=chunk.section_type,
            content=chunk.content,
            token_count=chunk.token_count,
            embedding=vector,
            chunk_metadata=dict(chunk.metadata or {}),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        rows.append(row)
    await db.flush()
    return rows


async def update_chunk_content(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    chunk_id: uuid.UUID,
    new_content: str,
    new_section_type: MasterResumeSectionType | None = None,
    new_metadata: dict[str, Any] | None = None,
) -> MasterResumeChunk | None:
    """Edit a single chunk in place and re-embed it.

    Used by ``PATCH /api/profile/resume/chunks/{id}``.  Re-embedding
    only the touched chunk (instead of the full resume) matches §18.4
    "Re-embedding strategy".
    """
    chunk = await get_chunk(db, user_id=user_id, chunk_id=chunk_id)
    if chunk is None:
        return None

    cleaned = (new_content or "").strip()
    if not cleaned:
        # Empty content is the documented way to delete a chunk via PATCH;
        # callers that want delete semantics should use the DELETE
        # endpoint, but we tolerate the alias here.
        await delete_chunk(db, user_id=user_id, chunk_id=chunk_id)
        return None

    chunk.content = cleaned
    chunk.token_count = count_tokens(cleaned)
    if new_section_type is not None:
        chunk.section_type = new_section_type
    if new_metadata is not None:
        chunk.chunk_metadata = dict(new_metadata)
    chunk.updated_at = _utcnow()

    # Re-embed just this chunk (single-element batch).
    [vector] = await embed_texts([cleaned])
    chunk.embedding = vector

    # Mirror the parent's bookkeeping.
    resume = await db.get(MasterResume, chunk.master_resume_id)
    if resume is not None:
        resume.last_embedded_at = _utcnow()
        resume.updated_at = _utcnow()

    await db.flush()
    return chunk


async def delete_chunk(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    chunk_id: uuid.UUID,
) -> bool:
    """Soft-delete ``chunk_id`` (no-op if already deleted or unknown).

    Returns ``True`` when a live chunk transitioned to deleted state.
    """
    chunk = await get_chunk(db, user_id=user_id, chunk_id=chunk_id)
    if chunk is None:
        return False
    chunk.deleted_at = _utcnow()
    chunk.updated_at = chunk.deleted_at

    resume = await db.get(MasterResume, chunk.master_resume_id)
    if resume is not None:
        # Drop the chunk-count cache by one so the UI shows the new
        # value without forcing a full recount.  Re-embedding window
        # stays as-is — deletion is not a re-embed.
        resume.chunk_count = max(0, resume.chunk_count - 1)
        resume.updated_at = _utcnow()

    await db.flush()
    return True


# ---------------------------------------------------------------------------
# Helpers used by the retrieval service
# ---------------------------------------------------------------------------


async def has_any_live_chunk(
    db: AsyncSession, *, user_id: uuid.UUID
) -> bool:
    """Cheap existence check used by the 409 ``master_resume_required`` gate."""
    row = (
        await db.execute(
            select(MasterResumeChunk.id)
            .where(MasterResumeChunk.user_id == user_id)
            .where(MasterResumeChunk.deleted_at.is_(None))
            .limit(1)
        )
    ).first()
    return row is not None


def iter_chunk_summaries(
    rows: Iterable[MasterResumeChunk],
) -> list[dict[str, Any]]:
    """Project ORM rows into the shape returned by the list endpoint."""
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": str(r.id),
                "section_type": r.section_type.value,
                "content": r.content,
                "token_count": r.token_count,
                "metadata": r.chunk_metadata,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None,
            }
        )
    return out


__all__ = [
    "delete_chunk",
    "get_chunk",
    "get_chunks_for_user",
    "get_raw_resume",
    "has_any_live_chunk",
    "iter_chunk_summaries",
    "replace_all_chunks",
    "update_chunk_content",
]
