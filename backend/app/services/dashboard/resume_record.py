"""Resume record upsert from agent session outputs (Step 27)."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import (
    AtsRecalcType,
    AtsScoreHistory,
    ResumeRecord,
    ResumeRecordStatus,
)
from app.models.session import Session


def compute_jd_text_hash(jd_text: str) -> str:
    normalized = " ".join(jd_text.split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def extract_jd_metadata(session: Session) -> tuple[str, str]:
    """Best-effort job title + company from session context."""
    title = ""
    company = ""

    if session.user_info and session.user_info.target_role.strip():
        title = session.user_info.target_role.strip()
    elif session.phase1_output and session.phase1_output.role_context.primary_domain:
        title = session.phase1_output.role_context.primary_domain.strip()

    jd = session.jd_raw or ""
    company_patterns = [
        r"(?:at|@)\s+([A-Z][A-Za-z0-9&.\- ]{1,80}?)(?:\s|,|\.|\n|$)",
        r"(?:company|employer)\s*:\s*([A-Za-z0-9&.\- ]{1,80})",
    ]
    for pattern in company_patterns:
        match = re.search(pattern, jd, re.IGNORECASE)
        if match:
            company = match.group(1).strip()
            break

    if not title:
        first_line = jd.strip().split("\n")[0][:200] if jd.strip() else ""
        title = first_line or "Untitled role"
    if not company:
        company = "Unknown"

    return title, company


async def upsert_resume_record_from_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session: Session,
    ats_score: int,
    recalc_type: AtsRecalcType = AtsRecalcType.initial,
) -> ResumeRecord:
    """Create or update a ResumeRecord keyed by (user_id, jd_text_hash)."""
    jd_text = session.jd_raw or ""
    if not jd_text.strip():
        raise ValueError("Session has no job description text")

    jd_hash = compute_jd_text_hash(jd_text)
    jd_title, jd_company = extract_jd_metadata(session)
    now = datetime.now(timezone.utc)

    existing = (
        await db.execute(
            select(ResumeRecord).where(
                ResumeRecord.user_id == user_id,
                ResumeRecord.jd_text_hash == jd_hash,
                ResumeRecord.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        record = ResumeRecord(
            user_id=user_id,
            session_id=session.session_id,
            jd_title=jd_title,
            jd_company=jd_company,
            jd_text_hash=jd_hash,
            tags=[],
            current_ats_score=ats_score,
            starting_ats_score=ats_score,
            status=ResumeRecordStatus.draft,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        await db.flush()
        db.add(
            AtsScoreHistory(
                resume_record_id=record.id,
                score=ats_score,
                recalc_type=AtsRecalcType.initial,
                triggered_at=now,
            )
        )
        return record

    existing.session_id = session.session_id
    existing.jd_title = jd_title
    existing.jd_company = jd_company
    existing.current_ats_score = ats_score
    existing.updated_at = now

    if recalc_type == AtsRecalcType.initial:
        recalc_type = AtsRecalcType.auto

    db.add(
        AtsScoreHistory(
            resume_record_id=existing.id,
            score=ats_score,
            recalc_type=recalc_type,
            triggered_at=now,
        )
    )
    return existing
