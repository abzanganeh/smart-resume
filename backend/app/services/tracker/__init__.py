"""Application tracker service layer."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.dashboard import ResumeRecord
from app.models.tracker import (
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENT_TOTAL_BYTES,
    MAX_ATTACHMENTS_PER_APPLICATION,
    Application,
    ApplicationAttachment,
    ApplicationStatus,
    InterviewRound,
    OfferDetail,
)

# Rolling window for duplicate detection.  We only flag apps as duplicates
# if the same (title, company) pair appears within this many days of an
# existing row — older matches are treated as intentional new applications
# to the same role (e.g. re-applying six months later).
DUPLICATE_LOOKBACK_DAYS = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def append_status_history(
    app: Application,
    *,
    status: ApplicationStatus,
    at: datetime | None = None,
) -> None:
    history = list(app.status_history or [])
    history.append(
        {
            "status": status.value,
            "at": (at or _utcnow()).isoformat(),
        }
    )
    app.status_history = history


async def get_owned_application(
    db: AsyncSession,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
    *,
    load_relations: bool = False,
) -> Application:
    query = select(Application).where(
        Application.id == application_id,
        Application.user_id == user_id,
    )
    if load_relations:
        query = query.options(
            selectinload(Application.interview_rounds),
            selectinload(Application.offer_detail),
            selectinload(Application.attachments),
        )
    app = (await db.execute(query)).scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


async def resolve_title_company(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    resume_record_id: uuid.UUID | None,
    jd_title: str | None,
    jd_company: str | None,
) -> tuple[str, str, uuid.UUID | None]:
    if resume_record_id is not None:
        record = (
            await db.execute(
                select(ResumeRecord).where(
                    ResumeRecord.id == resume_record_id,
                    ResumeRecord.user_id == user_id,
                    ResumeRecord.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if record is None:
            raise HTTPException(status_code=404, detail="Resume record not found")
        existing = (
            await db.execute(
                select(Application.id).where(
                    Application.resume_record_id == resume_record_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="An application is already linked to this resume record",
            )
        return record.jd_title, record.jd_company, resume_record_id

    title = (jd_title or "").strip()
    company = (jd_company or "").strip()
    if not title or not company:
        raise HTTPException(
            status_code=422,
            detail="jd_title and jd_company are required when resume_record_id is omitted",
        )
    return title, company, None


def build_timeline(app: Application) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for entry in app.status_history or []:
        events.append(
            {
                "type": "status_change",
                "at": entry.get("at"),
                "status": entry.get("status"),
            }
        )

    for rnd in app.interview_rounds:
        events.append(
            {
                "type": "interview_round",
                "at": (rnd.scheduled_at or rnd.created_at).isoformat(),
                "round_id": str(rnd.id),
                "name": rnd.name,
                "format": rnd.format.value,
                "outcome": rnd.outcome.value if rnd.outcome else None,
            }
        )

    for att in app.attachments:
        events.append(
            {
                "type": "attachment",
                "at": att.uploaded_at.isoformat(),
                "attachment_id": str(att.id),
                "filename": att.filename,
                "size_bytes": att.size_bytes,
            }
        )

    if app.notes:
        events.append(
            {
                "type": "notes",
                "at": app.updated_at.isoformat(),
                "notes": app.notes,
            }
        )

    events.sort(key=lambda e: e.get("at") or "")
    return events


async def next_round_number(db: AsyncSession, application_id: uuid.UUID) -> int:
    current = (
        await db.execute(
            select(func.coalesce(func.max(InterviewRound.round_number), 0)).where(
                InterviewRound.application_id == application_id
            )
        )
    ).scalar_one()
    return int(current) + 1


async def attachment_usage(db: AsyncSession, application_id: uuid.UUID) -> tuple[int, int]:
    count, total = (
        await db.execute(
            select(
                func.count(ApplicationAttachment.id),
                func.coalesce(func.sum(ApplicationAttachment.size_bytes), 0),
            ).where(ApplicationAttachment.application_id == application_id)
        )
    ).one()
    return int(count), int(total)


async def validate_attachment_upload(
    db: AsyncSession,
    application_id: uuid.UUID,
    size_bytes: int,
) -> None:
    if size_bytes > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Attachment exceeds {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB limit",
        )
    count, total = await attachment_usage(db, application_id)
    if count >= MAX_ATTACHMENTS_PER_APPLICATION:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum {MAX_ATTACHMENTS_PER_APPLICATION} attachments per application",
        )
    if total + size_bytes > MAX_ATTACHMENT_TOTAL_BYTES:
        raise HTTPException(
            status_code=422,
            detail="Total attachment size would exceed 25 MB per application",
        )


async def list_applications(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: ApplicationStatus | None = None,
    company: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    archived: bool | None = False,
) -> list[Application]:
    """List a user's applications.

    ``archived=False`` (default) returns only active rows; ``archived=True``
    returns only archived rows; ``archived=None`` returns both.
    """
    query = select(Application).where(Application.user_id == user_id)
    if status is not None:
        query = query.where(Application.status == status)
    if company:
        pattern = f"%{company.lower()}%"
        query = query.where(func.lower(Application.jd_company).like(pattern))
    if date_from is not None:
        query = query.where(Application.created_at >= date_from)
    if date_to is not None:
        query = query.where(Application.created_at <= date_to)
    if archived is False:
        query = query.where(Application.archived_at.is_(None))
    elif archived is True:
        query = query.where(Application.archived_at.is_not(None))
    query = query.order_by(desc(Application.updated_at))
    return list((await db.execute(query)).scalars().all())


_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def normalize_for_dedupe(value: str | None) -> str:
    """Lowercase + collapse non-alphanumerics so 'Google, Inc.' collides with
    'google inc' when detecting duplicate applications."""
    if not value:
        return ""
    return _NORMALIZE_RE.sub(" ", value.lower()).strip()


async def count_active_applications(
    db: AsyncSession, user_id: uuid.UUID
) -> int:
    """Count non-archived applications for the user (any status)."""
    count = (
        await db.execute(
            select(func.count(Application.id)).where(
                Application.user_id == user_id,
                Application.archived_at.is_(None),
            )
        )
    ).scalar_one()
    return int(count)


def _sql_normalize(column: Any) -> Any:
    """SQL expression equivalent of :func:`normalize_for_dedupe`."""
    return func.trim(
        func.regexp_replace(func.lower(column), r"[^a-z0-9]+", " ", "g")
    )


async def find_duplicate_application(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    jd_title: str,
    jd_company: str,
    now: datetime | None = None,
) -> Application | None:
    """Return an existing recent application with matching normalized
    (title, company), or ``None`` if there is no duplicate.

    Archived rows do not trigger duplicate detection — if the user
    intentionally archived the original, they can re-open a new one
    without a warning.  The match window is
    :data:`DUPLICATE_LOOKBACK_DAYS` days from ``now``.
    """
    normalized_title = normalize_for_dedupe(jd_title)
    normalized_company = normalize_for_dedupe(jd_company)
    if not normalized_title or not normalized_company:
        return None
    cutoff = (now or _utcnow()) - timedelta(days=DUPLICATE_LOOKBACK_DAYS)
    stmt = (
        select(Application)
        .where(
            Application.user_id == user_id,
            Application.archived_at.is_(None),
            Application.created_at >= cutoff,
            _sql_normalize(Application.jd_title) == normalized_title,
            _sql_normalize(Application.jd_company) == normalized_company,
        )
        .order_by(desc(Application.created_at))
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def application_funnel_counts(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[str, int]:
    """Aggregate application counts grouped by status, plus derived totals.

    Returned dict shape::

        {
            "draft": N, "applied": N, "interviewing": N, "offer": N,
            "accepted": N, "rejected": N, "withdrawn": N,
            "active_total": N,   # non-archived rows, any status
            "archived_total": N, # archived rows
            "total": N,          # active + archived
        }
    """
    per_status_stmt = (
        select(
            Application.status,
            Application.archived_at.is_not(None).label("is_archived"),
            func.count(Application.id).label("cnt"),
        )
        .where(Application.user_id == user_id)
        .group_by(Application.status, "is_archived")
    )
    rows = (await db.execute(per_status_stmt)).all()
    counts: dict[str, int] = {s.value: 0 for s in ApplicationStatus}
    active_total = 0
    archived_total = 0
    for status, is_archived, cnt in rows:
        cnt_int = int(cnt)
        if is_archived:
            archived_total += cnt_int
        else:
            counts[status.value] += cnt_int
            active_total += cnt_int
    counts["active_total"] = active_total
    counts["archived_total"] = archived_total
    counts["total"] = active_total + archived_total
    return counts


__all__ = [
    "DUPLICATE_LOOKBACK_DAYS",
    "append_status_history",
    "application_funnel_counts",
    "attachment_usage",
    "build_timeline",
    "count_active_applications",
    "find_duplicate_application",
    "get_owned_application",
    "list_applications",
    "next_round_number",
    "normalize_for_dedupe",
    "resolve_title_company",
    "validate_attachment_upload",
]
