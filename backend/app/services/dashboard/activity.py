"""Recent activity feed builder for dashboard summary (§19.3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import Notification
from app.models.dashboard import AtsRecalcType, AtsScoreHistory, ResumeRecord
from app.models.jobs import JobSearchLog, SavedJob
from app.models.user import CreditTransaction


async def build_recent_activity(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Aggregate last events from resume, ATS, credits, jobs, notifications."""
    events: list[dict[str, Any]] = []

    resume_rows = (
        await db.execute(
            select(ResumeRecord)
            .where(
                ResumeRecord.user_id == user_id,
                ResumeRecord.deleted_at.is_(None),
            )
            .order_by(desc(ResumeRecord.updated_at))
            .limit(limit)
        )
    ).scalars().all()
    for row in resume_rows:
        events.append(
            {
                "type": "resume_built",
                "at": row.updated_at,
                "title": f"Resume built for {row.jd_title}",
                "subtitle": row.jd_company,
                "meta": {
                    "resume_id": str(row.id),
                    "ats_score": row.current_ats_score,
                },
            }
        )

    score_rows = (
        await db.execute(
            select(AtsScoreHistory, ResumeRecord)
            .join(ResumeRecord, AtsScoreHistory.resume_record_id == ResumeRecord.id)
            .where(
                ResumeRecord.user_id == user_id,
                ResumeRecord.deleted_at.is_(None),
                AtsScoreHistory.recalc_type != AtsRecalcType.initial,
            )
            .order_by(desc(AtsScoreHistory.triggered_at))
            .limit(limit)
        )
    ).all()
    for history, record in score_rows:
        events.append(
            {
                "type": "ats_recalc",
                "at": history.triggered_at,
                "title": f"ATS score updated to {history.score}",
                "subtitle": f"{record.jd_title} at {record.jd_company}",
                "meta": {
                    "resume_id": str(record.id),
                    "score": history.score,
                    "recalc_type": history.recalc_type.value,
                },
            }
        )

    credit_rows = (
        await db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
            .order_by(desc(CreditTransaction.created_at))
            .limit(limit)
        )
    ).scalars().all()
    for tx in credit_rows:
        if tx.delta == 0:
            continue
        events.append(
            {
                "type": "payment" if tx.stripe_event_id else "credit",
                "at": tx.created_at,
                "title": (tx.reason or tx.action.value).replace("_", " ").title(),
                "subtitle": f"{'+' if tx.delta > 0 else ''}{tx.delta} credits",
                "meta": {"action": tx.action.value},
            }
        )

    notif_rows = (
        await db.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(desc(Notification.created_at))
            .limit(limit)
        )
    ).scalars().all()
    for note in notif_rows:
        data = note.data or {}
        events.append(
            {
                "type": "notification",
                "at": note.created_at,
                "title": note.title or data.get("title") or note.type.replace("_", " ").title(),
                "subtitle": note.body or data.get("body", ""),
                "meta": {"notification_type": note.type},
            }
        )

    saved_job_count = (
        await db.execute(
            select(SavedJob)
            .where(SavedJob.user_id == user_id)
            .order_by(desc(SavedJob.created_at))
            .limit(limit)
        )
    ).scalars().all()
    for saved in saved_job_count:
        events.append(
            {
                "type": "job_saved",
                "at": saved.created_at,
                "title": "Job bookmarked",
                "subtitle": "",
                "meta": {"job_cache_id": str(saved.job_cache_id)},
            }
        )

    search_rows = (
        await db.execute(
            select(JobSearchLog)
            .where(JobSearchLog.user_id == user_id)
            .order_by(desc(JobSearchLog.created_at))
            .limit(limit)
        )
    ).scalars().all()
    for search in search_rows:
        events.append(
            {
                "type": "job_search",
                "at": search.created_at,
                "title": f"Searched jobs: {search.query}",
                "subtitle": f"{search.result_count} results",
                "meta": {"source": search.source.value},
            }
        )

    events.sort(key=lambda e: e["at"], reverse=True)
    trimmed = events[:limit]
    for item in trimmed:
        at = item["at"]
        item["at"] = at.isoformat() if isinstance(at, datetime) else at
    return trimmed
