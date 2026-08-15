"""Poll watched companies and upsert career job cache rows."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.career_watch import CareerJobCache, WatchedCompany
from app.services.career_watch.poll_schedule import fetch_due_companies
from app.services.career_watch.registry import fetch_company_jobs

log = structlog.get_logger("career_watch.poller")


def _description_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PollStats:
    companies_polled: int = 0
    jobs_upserted: int = 0
    failures: int = 0


async def poll_company(
    session: AsyncSession,
    company: WatchedCompany,
    *,
    client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
) -> int:
    """Fetch jobs for ``company`` and upsert cache rows. Returns upsert count."""
    now = now or datetime.now(timezone.utc)
    upserted = 0
    try:
        jobs = await fetch_company_jobs(company, client=client)
    except Exception as exc:  # noqa: BLE001
        company.poll_fail_count += 1
        company.updated_at = now
        await session.flush()
        log.warning(
            "career_watch_poll_failed",
            company_id=str(company.id),
            error=str(exc),
        )
        raise

    seen_ids: set[str] = set()
    for job in jobs:
        seen_ids.add(job.external_job_id)
        existing = (
            await session.execute(
                select(CareerJobCache)
                .where(CareerJobCache.watched_company_id == company.id)
                .where(CareerJobCache.external_job_id == job.external_job_id)
            )
        ).scalar_one_or_none()
        desc_hash = _description_hash(job.description_text)
        if existing is None:
            session.add(
                CareerJobCache(
                    id=uuid.uuid4(),
                    watched_company_id=company.id,
                    external_job_id=job.external_job_id,
                    title=job.title,
                    location=job.location,
                    apply_url=job.apply_url,
                    description_text=job.description_text,
                    description_hash=desc_hash,
                    posted_at=job.posted_at,
                    first_seen_at=now,
                    last_seen_at=now,
                    is_open=True,
                    raw_payload=job.raw_payload,
                )
            )
            upserted += 1
        else:
            existing.title = job.title
            existing.location = job.location
            existing.apply_url = job.apply_url
            existing.description_text = job.description_text
            existing.description_hash = desc_hash
            existing.posted_at = job.posted_at
            existing.last_seen_at = now
            existing.is_open = True
            existing.raw_payload = job.raw_payload

    stale = (
        await session.execute(
            select(CareerJobCache)
            .where(CareerJobCache.watched_company_id == company.id)
            .where(CareerJobCache.is_open.is_(True))
        )
    ).scalars().all()
    for row in stale:
        if row.external_job_id not in seen_ids:
            row.is_open = False

    company.last_polled_at = now
    company.poll_fail_count = 0
    company.updated_at = now
    await session.flush()
    return upserted


async def poll_due_companies(
    session: AsyncSession,
    *,
    limit: int = 50,
    now: datetime | None = None,
) -> PollStats:
    """Poll companies due per watcher tier limits (min interval across watchers)."""
    now = now or datetime.now(timezone.utc)
    companies = await fetch_due_companies(session, limit=limit, now=now)
    stats = PollStats()
    async with httpx.AsyncClient() as client:
        for company in companies:
            try:
                count = await poll_company(session, company, client=client, now=now)
                stats.companies_polled += 1
                stats.jobs_upserted += count
            except Exception:
                stats.failures += 1
    return stats


__all__ = ["PollStats", "poll_company", "poll_due_companies"]
