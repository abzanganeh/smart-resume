"""Resume record upsert from agent session outputs (Step 27)."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import (
    AtsRecalcType,
    AtsScoreHistory,
    ResumeRecord,
    ResumeRecordStatus,
    TailoringStage,
)
from app.models.session import Session

log = logging.getLogger(__name__)


def compute_jd_text_hash(jd_text: str) -> str:
    normalized = " ".join(jd_text.split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def compute_session_placeholder_hash(session_id: str) -> str:
    return hashlib.sha256(f"session:{session_id}".encode()).hexdigest()


_JOB_TITLE_WORDS = re.compile(
    r"\b("
    r"Senior|Junior|Staff|Principal|Lead|Director|Manager|"
    r"Engineer|Developer|Designer|Analyst|Scientist|Architect|"
    r"AI|ML|Software|Backend|Frontend|Full[\s-]?Stack"
    r")\b",
    re.IGNORECASE,
)

_LOCATION_HINT = re.compile(
    r",\s*[A-Z]{2}\b|\b(WA|CA|NY|TX|Remote|Hybrid|United States)\b",
    re.IGNORECASE,
)

_JUNK_LINE = frozenset(
    {
        "apply now",
        "save job",
        "share this job",
        "unknown",
        "remote",
        "hybrid",
    }
)


def _looks_like_job_title(text: str) -> bool:
    return bool(_JOB_TITLE_WORDS.search(text))


def _looks_like_location(text: str) -> bool:
    return bool(_LOCATION_HINT.search(text))


def _looks_like_company_name(text: str) -> bool:
    cleaned = text.strip().rstrip(".,")
    if not cleaned or len(cleaned) < 2:
        return False
    if cleaned.lower() in _JUNK_LINE:
        return False
    if _looks_like_job_title(cleaned):
        return False
    if not re.match(r"^[A-Z0-9]", cleaned):
        return False
    words = cleaned.split()
    has_org_suffix = bool(
        re.search(
            r"\b(Investments|Inc|Corp|LLC|Ltd|Group|Technologies|Technology|Solutions|Services)\.?\b",
            cleaned,
            re.IGNORECASE,
        )
    )
    return len(words) >= 2 or has_org_suffix


def _company_from_jd_text(jd: str) -> str:
    """Extract employer name from scraped or pasted job descriptions."""
    jd = jd.strip()
    if not jd:
        return ""

    patterns = [
        (
            r"(?:at|@|join)\s+"
            r"([A-Z][A-Za-z0-9&.\-' ]+?"
            r"(?:Investments|Inc\.?|Corp\.?|LLC|Ltd\.?|Group|"
            r"Technologies|Technology|Solutions|Services)?)"
            r"(?=\s+(?:to|for|and|who|that|build|develop|work|our|the)\b|[,\.\n]|$)"
        ),
        r"(?:company|employer)\s*:\s*([A-Za-z0-9&.\-' ]{1,80})",
        (
            r"\b([A-Z][A-Za-z0-9&.\-' ]+?\s+"
            r"(?:Investments|Inc\.?|Corp\.?|LLC|Ltd\.?|Group|"
            r"Technologies|Technology|Solutions|Services))\b"
        ),
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, jd[:4000], re.IGNORECASE):
            name = match.group(1).strip().rstrip(".,")
            if _looks_like_company_name(name):
                return name

    lines = [line.strip() for line in jd.splitlines() if line.strip()]
    if len(lines) >= 2 and _looks_like_company_name(lines[1]) and not _looks_like_location(lines[1]):
        return lines[1]

    candidates = re.findall(
        r"\b([A-Z][a-z]+(?: [A-Z][a-z]+){0,4}"
        r"(?: Investments| Inc| Corp| LLC| Ltd| Group|"
        r" Technologies| Technology| Solutions| Services)?)\b",
        jd[:4000],
    )
    filtered = [
        candidate
        for candidate in candidates
        if _looks_like_company_name(candidate) and not _looks_like_job_title(candidate)
    ]
    if filtered:
        return Counter(filtered).most_common(1)[0][0]
    return ""


def resolve_company_name(session: Session) -> str:
    """Best-effort employer name for company intel, naming, and dashboard metadata."""
    if session.company_intel and session.company_intel.company_name.strip():
        name = session.company_intel.company_name.strip()
        if name.lower() != "unknown":
            return name

    if session.phase3_output is not None:
        contact = session.phase3_output.contact or {}
        if isinstance(contact, dict):
            from_phase3 = str(contact.get("company") or "").strip()
            if from_phase3 and from_phase3.lower() != "unknown":
                return from_phase3

    from_jd = _company_from_jd_text(session.jd_raw or "")
    if from_jd:
        return from_jd

    return "Unknown"


def extract_jd_metadata(session: Session) -> tuple[str, str]:
    """Best-effort job title + company from session context."""
    title = ""

    if session.user_info and session.user_info.target_role.strip():
        title = session.user_info.target_role.strip()
    elif session.phase1_output and session.phase1_output.role_context.primary_domain:
        title = session.phase1_output.role_context.primary_domain.strip()

    jd = session.jd_raw or ""
    if not title:
        first_line = jd.strip().split("\n")[0][:200] if jd.strip() else ""
        title = first_line or "Untitled role"

    company = resolve_company_name(session)
    return title, company


def default_record_title(session: Session) -> tuple[str, str]:
    if session.user_info and session.user_info.target_role.strip():
        return session.user_info.target_role.strip(), "—"
    if session.resume_parsed and session.resume_parsed.contact.name.strip():
        return f"{session.resume_parsed.contact.name.strip()} — resume draft", "—"
    return "Resume draft", "—"


async def _find_record_for_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: str,
) -> ResumeRecord | None:
    return (
        await db.execute(
            select(ResumeRecord).where(
                ResumeRecord.user_id == user_id,
                ResumeRecord.session_id == session_id,
                ResumeRecord.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def ensure_in_progress_resume_record(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session: Session,
) -> ResumeRecord | None:
    """Create or refresh a dashboard row for an in-flight tailoring session."""
    jd_text = (session.jd_raw or "").strip()
    has_resume = bool(
        (session.resume_raw or "").strip()
        or session.resume_parsed is not None
    )
    if not jd_text and not has_resume:
        return None

    if jd_text:
        jd_hash = compute_jd_text_hash(jd_text)
        jd_title, jd_company = extract_jd_metadata(session)
    else:
        jd_hash = compute_session_placeholder_hash(session.session_id)
        jd_title, jd_company = default_record_title(session)

    now = datetime.now(timezone.utc)
    record = await _find_record_for_session(
        db, user_id=user_id, session_id=session.session_id
    )

    if record is None:
        record = (
            await db.execute(
                select(ResumeRecord).where(
                    ResumeRecord.user_id == user_id,
                    ResumeRecord.jd_text_hash == jd_hash,
                    ResumeRecord.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    if record is None:
        record = ResumeRecord(
            user_id=user_id,
            session_id=session.session_id,
            jd_title=jd_title,
            jd_company=jd_company,
            jd_text_hash=jd_hash,
            tags=[],
            current_ats_score=0,
            starting_ats_score=0,
            status=ResumeRecordStatus.draft,
            tailoring_stage=TailoringStage.in_progress,
            display_name=None,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        return record

    record.session_id = session.session_id
    record.jd_text_hash = jd_hash
    record.jd_title = jd_title
    record.jd_company = jd_company
    record.updated_at = now
    return record


async def mark_resume_record_polished(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: str,
) -> ResumeRecord | None:
    record = await _find_record_for_session(
        db, user_id=user_id, session_id=session_id
    )
    if record is None:
        return None
    record.tailoring_stage = TailoringStage.polished
    record.updated_at = datetime.now(timezone.utc)
    return record


async def sync_dashboard_record_from_session(session: Session) -> None:
    """Best-effort dashboard sync after wizard steps (upload, JD, user info)."""
    if not session.user_id:
        return
    try:
        user_id = uuid.UUID(session.user_id)
    except ValueError:
        return

    from app.db.engine import async_session_factory

    try:
        async with async_session_factory() as db:
            await ensure_in_progress_resume_record(
                db, user_id=user_id, session=session
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — must not fail wizard steps
        log.warning(
            "dashboard_record_sync_failed",
            extra={"session_id": session.session_id, "error": str(exc)},
        )


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

    existing = await _find_record_for_session(
        db, user_id=user_id, session_id=session.session_id
    )
    if existing is None:
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
            tailoring_stage=TailoringStage.polished,
            display_name=None,
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

    had_scores = existing.current_ats_score > 0 or existing.starting_ats_score > 0
    existing.session_id = session.session_id
    existing.jd_title = jd_title
    existing.jd_company = jd_company
    existing.jd_text_hash = jd_hash
    existing.current_ats_score = ats_score
    if not had_scores:
        existing.starting_ats_score = ats_score
    existing.tailoring_stage = TailoringStage.polished
    existing.updated_at = now

    if recalc_type == AtsRecalcType.initial and had_scores:
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
