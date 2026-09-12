"""Persist tailoring session snapshots on resume_records for Redis restore."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit import AuditOutput
from app.models.cover_letter import CoverLetterOutput
from app.models.dashboard import ResumeRecord, TailoringStage
from app.models.job_description import JobDescription
from app.models.keywords import KeywordExtractionOutput
from app.models.master_resume import MasterResume
from app.models.qa import QAOutput
from app.models.resume import ParsedResume
from app.models.rewrite import TailoredResumeOutput
from app.models.session import PhaseStatus, Session
from app.models.userinfo import UserInfo
from app.services.checkup_service import parsed_to_tailored
from app.services.dashboard.resume_record import _find_record_for_session
from app.services.session_store import get_session, update_session

log = structlog.get_logger("session_cache")


def _dump_model(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump_json"):
        return json.loads(value.model_dump_json())
    return value


def build_session_cache(session: Session) -> dict[str, Any] | None:
    """Serialize restorable session fields. Requires a completed tailored rewrite."""
    if session.phase3_output is None:
        return None
    cache: dict[str, Any] = {
        "tailored_output": _dump_model(session.phase3_output),
        "jd_raw": session.jd_raw,
        "resume_raw": session.resume_raw,
        "resume_parsed": _dump_model(session.resume_parsed),
        "user_info": _dump_model(session.user_info),
        "user_claimed_keywords": list(session.user_claimed_keywords or []),
        "user_extra_notes": session.user_extra_notes or "",
        "bullet_fixes": [bf.model_dump() for bf in (session.bullet_fixes or [])],
        "approved_metrics": [am.model_dump() for am in (session.approved_metrics or [])],
        "phase1_output": _dump_model(session.phase1_output),
        "phase2_output": _dump_model(session.phase2_output),
        "phase4_output": _dump_model(session.phase4_output),
        "cover_letter_output": _dump_model(session.cover_letter_output),
        "provider": session.provider,
        "model": session.model,
    }
    return cache


async def persist_session_cache(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: str,
    session: Session,
) -> None:
    """Best-effort snapshot write after tailored rewrite or edits."""
    cache = build_session_cache(session)
    if cache is None:
        return
    now = datetime.now(timezone.utc)
    await db.execute(
        update(ResumeRecord)
        .where(
            ResumeRecord.user_id == user_id,
            ResumeRecord.session_id == session_id,
            ResumeRecord.deleted_at.is_(None),
        )
        .values(session_cache=cache, updated_at=now)
    )


async def sync_session_cache_for_session(
    db: AsyncSession,
    session: Session,
) -> None:
    """Persist Postgres snapshot whenever phase 3 output changes (logged-in users)."""
    if session.phase3_output is None or not session.user_id:
        return
    try:
        user_id = uuid.UUID(session.user_id)
    except ValueError:
        return
    await persist_session_cache(
        db,
        user_id=user_id,
        session_id=session.session_id,
        session=session,
    )


def _session_from_cache(
    session_id: str,
    user_id: uuid.UUID,
    cache: dict[str, Any],
) -> Session:
    now = datetime.now(timezone.utc)
    session = Session(
        session_id=session_id,
        user_id=str(user_id),
        created_at=now,
        expires_at=now + timedelta(seconds=settings.SESSION_TTL_SECONDS),
        provider=cache.get("provider"),
        model=cache.get("model"),
        jd_raw=cache.get("jd_raw"),
        resume_raw=cache.get("resume_raw"),
        user_extra_notes=str(cache.get("user_extra_notes") or ""),
        user_claimed_keywords=list(cache.get("user_claimed_keywords") or []),
    )
    if cache.get("resume_parsed"):
        session.resume_parsed = ParsedResume.model_validate(cache["resume_parsed"])
    if cache.get("user_info"):
        session.user_info = UserInfo.model_validate(cache["user_info"])
    if cache.get("bullet_fixes"):
        from app.models.session import BulletFix

        session.bullet_fixes = [BulletFix.model_validate(b) for b in cache["bullet_fixes"]]
    if cache.get("approved_metrics"):
        from app.models.session import ApprovedMetric

        session.approved_metrics = [
            ApprovedMetric.model_validate(m) for m in cache["approved_metrics"]
        ]
    if cache.get("phase1_output"):
        session.phase1_output = KeywordExtractionOutput.model_validate(
            cache["phase1_output"]
        )
        session.phase1_status = PhaseStatus.done
    if cache.get("phase2_output"):
        session.phase2_output = AuditOutput.model_validate(cache["phase2_output"])
        session.phase2_status = PhaseStatus.done
    if cache.get("tailored_output"):
        session.phase3_output = TailoredResumeOutput.model_validate(
            cache["tailored_output"]
        )
        session.phase3_status = PhaseStatus.done
    if cache.get("phase4_output"):
        session.phase4_output = QAOutput.model_validate(cache["phase4_output"])
        session.phase4_status = PhaseStatus.done
    if cache.get("cover_letter_output"):
        session.cover_letter_output = CoverLetterOutput.model_validate(
            cache["cover_letter_output"]
        )
    return session


def _parsed_from_master_sections(sections: dict[str, Any]) -> ParsedResume:
    return ParsedResume.model_validate(
        {
            "contact": sections.get("contact") or {},
            "summary": sections.get("summary"),
            "skills": list(sections.get("skills") or []),
            "experience": list(sections.get("experience") or []),
            "projects": list(sections.get("projects") or []),
            "education": list(sections.get("education") or []),
            "certifications": list(sections.get("certifications") or []),
        }
    )


async def build_legacy_session_cache(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    record: ResumeRecord,
) -> dict[str, Any] | None:
    """Rebuild a snapshot for polished rows created before session_cache existed.

    Uses the committed master resume (updated on export) plus the saved JD row
    linked to this tailoring session. Safe when the user has a single polished
    resume; multi-resume users may need a fresh Phase 3 run instead.
    """
    if record.tailoring_stage != TailoringStage.polished:
        return None

    master = (
        await db.execute(
            select(MasterResume).where(MasterResume.user_id == user_id)
        )
    ).scalar_one_or_none()
    if master is None or not master.parsed_sections:
        return None

    jd_row = (
        await db.execute(
            select(JobDescription)
            .where(
                JobDescription.user_id == user_id,
                JobDescription.session_id == record.session_id,
            )
            .order_by(JobDescription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if jd_row is None or not (jd_row.text or "").strip():
        return None

    try:
        parsed = _parsed_from_master_sections(dict(master.parsed_sections))
        tailored = parsed_to_tailored(parsed)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "session_cache.legacy_build_failed",
            session_id=record.session_id,
            error=str(exc),
        )
        return None

    cache = {
        "tailored_output": _dump_model(tailored),
        "jd_raw": jd_row.text,
        "resume_raw": master.raw_text or "",
        "resume_parsed": _dump_model(parsed),
        "user_claimed_keywords": [],
        "user_extra_notes": "",
        "bullet_fixes": [],
        "approved_metrics": [],
        "legacy_backfill": True,
    }
    log.info(
        "session_cache.legacy_built",
        session_id=record.session_id,
        user_id=str(user_id),
    )
    return cache


async def restore_session_from_record(
    db: AsyncSession,
    *,
    session_id: str,
    user_id: uuid.UUID,
) -> Session | None:
    """Rebuild a Redis session from the dashboard snapshot when TTL expired."""
    record = await _find_record_for_session(
        db, user_id=user_id, session_id=session_id
    )
    if record is None:
        return None
    cache = record.session_cache
    if not cache:
        cache = await build_legacy_session_cache(
            db, user_id=user_id, record=record
        )
        if cache is None:
            return None
        now = datetime.now(timezone.utc)
        await db.execute(
            update(ResumeRecord)
            .where(ResumeRecord.id == record.id)
            .values(session_cache=cache, updated_at=now)
        )
    tailored = cache.get("tailored_output")
    if not tailored:
        return None
    try:
        session = _session_from_cache(session_id, user_id, cache)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "session_cache.restore_parse_failed",
            session_id=session_id,
            error=str(exc),
        )
        return None
    await update_session(session)
    log.info("session_cache.restored", session_id=session_id, user_id=str(user_id))
    return session


async def backfill_session_from_record_if_needed(
    db: AsyncSession,
    session: Session,
) -> Session:
    """Rehydrate missing phase3 output on a live Redis session from Postgres."""
    if session.phase3_output is not None or not session.user_id:
        return session
    try:
        user_id = uuid.UUID(session.user_id)
    except ValueError:
        return session
    record = await _find_record_for_session(
        db, user_id=user_id, session_id=session.session_id
    )
    if record is None:
        return session
    cache = record.session_cache
    if not cache:
        cache = await build_legacy_session_cache(
            db, user_id=user_id, record=record
        )
        if cache is None:
            return session
        now = datetime.now(timezone.utc)
        await db.execute(
            update(ResumeRecord)
            .where(ResumeRecord.id == record.id)
            .values(session_cache=cache, updated_at=now)
        )
    if not cache.get("tailored_output"):
        return session
    try:
        restored = _session_from_cache(session.session_id, user_id, cache)
    except Exception:
        return session
    # Preserve any fresher in-memory fields on the existing session.
    for field in (
        "jd_raw",
        "resume_raw",
        "resume_parsed",
        "user_info",
        "user_claimed_keywords",
        "user_extra_notes",
        "bullet_fixes",
        "approved_metrics",
        "phase1_output",
        "phase2_output",
        "phase3_output",
        "phase4_output",
        "cover_letter_output",
        "phase1_status",
        "phase2_status",
        "phase3_status",
        "phase4_status",
    ):
        if getattr(session, field) in (None, [], "", PhaseStatus.pending):
            setattr(session, field, getattr(restored, field))
    if restored.phase3_output is not None:
        session.phase3_output = restored.phase3_output
        session.phase3_status = PhaseStatus.done
    await update_session(session)
    return session
