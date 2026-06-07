"""Write text fragments from any source into the user's RAG corpus.

Every accepted user action that produces re-usable candidate text — a
Phase 3 output, an accepted bullet edit, a free-form note, or a claimed
keyword — should flow through :func:`embed_and_store` so it lands in
``user_corpus_chunks`` and becomes available for future Phase 3 retrieval.

Design goals:
- Caller fires-and-forgets: all functions are async and swallow
  non-critical errors so a corpus write failure never blocks a user
  facing response.
- Each call is idempotent within the same session: ``session_id``-scoped
  sources (``tailored_resume``, ``bullet_fix``) soft-delete prior rows
  for the same session before inserting fresh ones.
- Notes and claimed keywords are additive — they are never wiped unless
  the user explicitly removes them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from app.db.engine import async_session_factory
from app.models.user_corpus import CorpusSource, UserCorpusChunk
from app.services.master_resume.chunking import count_tokens
from app.services.master_resume.embedding import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    embed_texts,
)

log = structlog.get_logger("corpus_writer")

# Maximum characters accepted per free-text fragment before truncation.
# Keeps embedding cost predictable and prevents runaway context.
_MAX_FRAGMENT_CHARS = 1500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _truncate(text: str, max_chars: int = _MAX_FRAGMENT_CHARS) -> str:
    text = (text or "").strip()
    return text[:max_chars] if len(text) > max_chars else text


async def _soft_delete_session_source(
    db: Any,
    *,
    user_id: uuid.UUID,
    session_id: str,
    source: CorpusSource,
) -> None:
    """Soft-delete prior corpus chunks for a session-scoped source."""
    from sqlalchemy import select, update

    await db.execute(
        update(UserCorpusChunk)
        .where(
            UserCorpusChunk.user_id == user_id,
            UserCorpusChunk.session_id == session_id,
            UserCorpusChunk.corpus_source == source,
            UserCorpusChunk.deleted_at.is_(None),
        )
        .values(deleted_at=_utcnow())
    )


async def _insert_chunks(
    db: Any,
    *,
    user_id: uuid.UUID,
    session_id: str | None,
    source: CorpusSource,
    fragments: list[tuple[str, str | None, dict[str, Any]]],
) -> None:
    """Embed and insert a batch of (content, section_type, metadata) tuples.

    Each tuple represents one corpus chunk.  The function batches all
    embedding calls into a single API request.  Embedding failures fall
    back to zero-vectors so the text is always persisted.
    """
    if not fragments:
        return

    texts = [_truncate(f[0]) for f in fragments]
    non_empty_texts = [t for t in texts if t]
    if not non_empty_texts:
        return

    from app.models.master_resume import EMBEDDING_DIM

    try:
        vectors = await embed_texts(non_empty_texts)
    except (EmbeddingConfigurationError, EmbeddingProviderError) as exc:
        log.warning(
            "corpus_writer.embed_failed_fallback",
            source=source.value,
            count=len(non_empty_texts),
            error=str(exc),
        )
        vectors = [[0.0] * EMBEDDING_DIM for _ in non_empty_texts]

    vec_iter = iter(vectors)
    now = _utcnow()
    for text, (_, section_type, metadata) in zip(texts, fragments):
        if not text:
            continue
        vector = next(vec_iter)
        chunk = UserCorpusChunk(
            id=uuid.uuid4(),
            user_id=user_id,
            session_id=session_id,
            corpus_source=source,
            section_type=section_type,
            content=text,
            token_count=count_tokens(text),
            embedding=vector,
            chunk_metadata=metadata or {},
            created_at=now,
        )
        db.add(chunk)

    await db.flush()


# ---------------------------------------------------------------------------
# Public API — one function per corpus event
# ---------------------------------------------------------------------------


async def embed_tailored_resume(
    *,
    user_id: uuid.UUID,
    session_id: str,
    tailored_output: Any,  # TailoredResumeOutput — avoid circular import
) -> None:
    """Embed Phase 3 output bullets into the corpus after a successful run.

    Old tailored_resume chunks for this session are soft-deleted first so
    a re-run only keeps the latest output.
    """
    if not tailored_output:
        return

    fragments: list[tuple[str, str | None, dict[str, Any]]] = []

    summary = (getattr(tailored_output, "summary", "") or "").strip()
    if summary:
        fragments.append((summary, "summary", {}))

    for entry in getattr(tailored_output, "experience", []) or []:
        company = getattr(entry, "company", "") or ""
        title = getattr(entry, "title", "") or ""
        for idx, bullet in enumerate(getattr(entry, "bullets", []) or []):
            text = (bullet or "").strip()
            if text:
                fragments.append(
                    (
                        text,
                        "experience",
                        {"company": company, "title": title, "bullet_index": idx},
                    )
                )

    for entry in getattr(tailored_output, "projects", []) or []:
        # projects is list[dict]
        bullets = entry.get("bullets") or [] if isinstance(entry, dict) else []
        title = (entry.get("title") or entry.get("name") or "") if isinstance(entry, dict) else ""
        for idx, bullet in enumerate(bullets):
            text = (bullet or "").strip()
            if text:
                fragments.append(
                    (text, "project", {"title": title, "bullet_index": idx})
                )

    if not fragments:
        return

    try:
        async with async_session_factory() as db:
            await _soft_delete_session_source(
                db,
                user_id=user_id,
                session_id=session_id,
                source=CorpusSource.tailored_resume,
            )
            await _insert_chunks(
                db,
                user_id=user_id,
                session_id=session_id,
                source=CorpusSource.tailored_resume,
                fragments=fragments,
            )
            await db.commit()
    except Exception as exc:
        log.warning(
            "corpus_writer.embed_tailored_resume_failed",
            session_id=session_id,
            error=str(exc),
        )


async def embed_bullet_fix(
    *,
    user_id: uuid.UUID,
    session_id: str,
    bullet_text: str,
    company: str | None = None,
    bullet_index: int | None = None,
    section_type: str = "experience",
) -> None:
    """Embed a single accepted bullet fix into the corpus.

    Called when the user explicitly accepts a bullet suggestion from the
    audit phase.  Additive — does not wipe other bullet_fix chunks.
    """
    text = _truncate(bullet_text)
    if not text:
        return

    metadata: dict[str, Any] = {}
    if company:
        metadata["company"] = company
    if bullet_index is not None:
        metadata["bullet_index"] = bullet_index

    try:
        async with async_session_factory() as db:
            await _insert_chunks(
                db,
                user_id=user_id,
                session_id=session_id,
                source=CorpusSource.bullet_fix,
                fragments=[(text, section_type, metadata)],
            )
            await db.commit()
    except Exception as exc:
        log.warning(
            "corpus_writer.embed_bullet_fix_failed",
            session_id=session_id,
            error=str(exc),
        )


async def embed_user_notes(
    *,
    user_id: uuid.UUID,
    session_id: str | None,
    notes_text: str,
) -> None:
    """Embed a free-form user note block.

    Notes are additive.  A new call does NOT delete prior notes — if you
    need to replace them, soft-delete from the caller before calling this.
    """
    text = _truncate(notes_text)
    if not text:
        return

    try:
        async with async_session_factory() as db:
            await _insert_chunks(
                db,
                user_id=user_id,
                session_id=session_id,
                source=CorpusSource.user_note,
                fragments=[(text, None, {})],
            )
            await db.commit()
    except Exception as exc:
        log.warning(
            "corpus_writer.embed_user_notes_failed",
            session_id=session_id,
            error=str(exc),
        )


async def embed_claimed_keywords(
    *,
    user_id: uuid.UUID,
    session_id: str | None,
    keywords: list[str],
) -> None:
    """Embed claimed keywords as individual corpus chunks.

    Each keyword becomes its own tiny chunk so the ANN similarity
    distribution does not get diluted by batching all keywords into one.
    """
    fragments: list[tuple[str, str | None, dict[str, Any]]] = []
    for kw in keywords:
        text = _truncate(kw)
        if text:
            fragments.append((text, None, {"type": "claimed_keyword"}))

    if not fragments:
        return

    try:
        async with async_session_factory() as db:
            await _insert_chunks(
                db,
                user_id=user_id,
                session_id=session_id,
                source=CorpusSource.claimed_keyword,
                fragments=fragments,
            )
            await db.commit()
    except Exception as exc:
        log.warning(
            "corpus_writer.embed_claimed_keywords_failed",
            session_id=session_id,
            error=str(exc),
        )


__all__ = [
    "embed_bullet_fix",
    "embed_claimed_keywords",
    "embed_tailored_resume",
    "embed_user_notes",
]
