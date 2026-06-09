"""Persist polished tailored resume edits across Redis, master resume, and corpus."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import async_session_factory
from app.models.rewrite import TailoredResumeOutput
from app.services.contact_authority import apply_authoritative_contact
from app.services.corpus_writer import embed_tailored_resume
from app.services.export_service import render_txt
from app.services.master_resume.crud import get_chunks_for_user, get_raw_resume
from app.services.master_resume.embedding import embed_texts
from app.services.session_store import get_session, update_session

log = structlog.get_logger("tailored_persistence")


def _tailored_to_parsed_sections(tailored: TailoredResumeOutput) -> dict[str, Any]:
    return {
        "contact": dict(tailored.contact or {}),
        "summary": tailored.summary,
        "skills": list(tailored.skills or []),
        "experience": [
            {
                "title": e.title,
                "company": e.company,
                "dates": e.dates,
                "bullets": list(e.bullets or []),
            }
            for e in tailored.experience or []
        ],
        "projects": list(tailored.projects or []),
        "education": [
            {
                "degree": e.degree,
                "institution": e.institution,
                "year": e.year,
                "bullets": list(e.bullets or []),
            }
            for e in tailored.education or []
        ],
        "certifications": list(tailored.certifications or []),
    }


async def _sync_master_resume_chunks(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tailored: TailoredResumeOutput,
    raw_text: str,
) -> None:
    """Update master resume raw text + experience chunk metadata from polished output."""
    from app.services.master_resume.crud import _upsert_master_resume

    parsed = _tailored_to_parsed_sections(tailored)
    await _upsert_master_resume(
        db,
        user_id=user_id,
        raw_text=raw_text,
        parsed_sections=parsed,
    )

    exp_by_company = {e.company: e for e in tailored.experience if e.company}
    chunks = await get_chunks_for_user(db, user_id=user_id)
    reembed_ids: list[uuid.UUID] = []

    for chunk in chunks:
        meta = dict(chunk.chunk_metadata or {})
        company = str(meta.get("company") or "").strip()
        if not company or company not in exp_by_company:
            continue
        exp = exp_by_company[company]
        prev_dates = str(meta.get("dates") or "")
        prev_title = str(meta.get("title") or "")
        meta["dates"] = exp.dates
        meta["title"] = exp.title
        meta["company"] = exp.company
        chunk.chunk_metadata = meta
        if prev_dates != exp.dates or prev_title != exp.title:
            # Prefix bullet with role context so embeddings reflect corrected dates.
            bullet = (chunk.content or "").strip()
            prefix = f"{exp.title} | {exp.company} | {exp.dates}".strip(" |")
            if bullet and not bullet.startswith(prefix):
                chunk.content = f"{prefix}\n{bullet}"
                reembed_ids.append(chunk.id)

    if reembed_ids:
        to_embed = [
            (c.content or "").strip()
            for c in chunks
            if c.id in reembed_ids and (c.content or "").strip()
        ]
        if to_embed:
            vectors = await embed_texts(to_embed)
            idx = 0
            for chunk in chunks:
                if chunk.id in reembed_ids and (chunk.content or "").strip():
                    chunk.embedding = vectors[idx]
                    idx += 1

    resume = await get_raw_resume(db, user_id=user_id)
    if resume is not None:
        from datetime import datetime, timezone

        resume.updated_at = datetime.now(timezone.utc)
    await db.flush()


async def commit_tailored_resume(
    session_id: str,
    tailored: TailoredResumeOutput,
    *,
    user_id: str | None,
    account_email: str | None = None,
) -> None:
    """Save polished tailored output and propagate to durable stores."""
    session = await get_session(session_id)
    if session is None:
        raise ValueError("Session not found")

    if account_email is None and user_id:
        from app.services.contact_authority import resolve_account_email

        account_email = await resolve_account_email(user_id)

    corrected = apply_authoritative_contact(
        tailored,
        user_info=session.user_info,
        account_email=account_email,
    )

    session.phase3_output = corrected
    session.resume_raw = render_txt(session, account_email=account_email)
    await update_session(session)

    if not user_id or not user_id.strip():
        return

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return

    async def _db_sync() -> None:
        async with async_session_factory() as db:
            try:
                await _sync_master_resume_chunks(
                    db,
                    user_id=uid,
                    tailored=corrected,
                    raw_text=session.resume_raw or "",
                )
                await db.commit()
            except Exception as exc:
                await db.rollback()
                log.warning(
                    "tailored_persistence.master_sync_failed",
                    session_id=session_id,
                    error=str(exc),
                )

        await embed_tailored_resume(
            user_id=uid,
            session_id=session_id,
            tailored_output=corrected,
        )

    asyncio.create_task(_db_sync(), name=f"commit_tailored:{session_id}")
