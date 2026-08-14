"""Keyword filter and lightweight ranking for Career Watch alerts."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.career_watch import (
    CareerAlert,
    CareerAlertStatus,
    CareerJobCache,
    UserWatchedCompany,
)
from app.services.career_watch.notifications import emit_career_watch_alert

log = structlog.get_logger("career_watch.matcher")

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def keyword_match_score(keywords: list[str], job: CareerJobCache) -> tuple[float, str]:
    """Return ``(score, reason)`` based on keyword overlap."""
    if not keywords:
        return 0.5, "no keywords configured; default watch match"
    haystack = " ".join(
        [job.title, job.location, job.description_text]
    ).lower()
    tokens = _tokenize(haystack)
    hits = [kw for kw in keywords if kw.lower() in haystack or kw.lower() in tokens]
    if not hits:
        return 0.0, ""
    score = min(1.0, len(hits) / max(len(keywords), 1))
    return score, f"matched keywords: {', '.join(hits)}"


@dataclass(frozen=True, slots=True)
class MatchStats:
    watches_scanned: int = 0
    alerts_created: int = 0
    notifications_sent: int = 0


async def match_new_jobs_for_watch(
    session: AsyncSession,
    watch: UserWatchedCompany,
    *,
    since: datetime | None = None,
    min_score: float = 0.25,
) -> int:
    """Create alerts for newly seen jobs matching ``watch`` keywords."""
    since = since or datetime.now(timezone.utc)
    jobs = (
        await session.execute(
            select(CareerJobCache)
            .where(CareerJobCache.watched_company_id == watch.watched_company_id)
            .where(CareerJobCache.is_open.is_(True))
            .where(CareerJobCache.first_seen_at >= since - timedelta(days=7))
        )
    ).scalars().all()

    created = 0
    keywords = list(watch.keywords or [])
    for job in jobs:
        score, reason = keyword_match_score(keywords, job)
        if score < min_score:
            continue
        existing = (
            await session.execute(
                select(CareerAlert)
                .where(CareerAlert.user_id == watch.user_id)
                .where(CareerAlert.career_job_cache_id == job.id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        alert = CareerAlert(
            id=uuid.uuid4(),
            user_id=watch.user_id,
            user_watched_company_id=watch.id,
            career_job_cache_id=job.id,
            match_score=score,
            match_reason=reason,
            status=CareerAlertStatus.pending,
        )
        session.add(alert)
        created += 1
    if created:
        watch.last_matched_at = datetime.now(timezone.utc)
    await session.flush()
    return created


async def run_matcher(
    session: AsyncSession,
    *,
    limit: int = 200,
) -> MatchStats:
    """Scan active watches and enqueue alerts + notifications."""
    watches = list(
        (
            await session.execute(
                select(UserWatchedCompany)
                .where(UserWatchedCompany.is_active.is_(True))
                .limit(limit)
            )
        ).scalars()
    )
    stats = MatchStats()
    for watch in watches:
        stats.watches_scanned += 1
        created = await match_new_jobs_for_watch(session, watch)
        stats.alerts_created += created

    pending = list(
        (
            await session.execute(
                select(CareerAlert)
                .where(CareerAlert.status == CareerAlertStatus.pending)
                .limit(limit)
            )
        ).scalars()
    )
    for alert in pending:
        sent = await emit_career_watch_alert(session, alert)
        if sent:
            stats.notifications_sent += 1
    return stats


__all__ = ["MatchStats", "keyword_match_score", "match_new_jobs_for_watch", "run_matcher"]
