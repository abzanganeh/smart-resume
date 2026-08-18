"""Poll watched companies and upsert career job cache rows."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.career_watch import WatchedCompany
from app.services.career_watch.corpus_sync import sync_polled_jobs_to_caches
from app.services.career_watch.global_poll_schedule import fetch_due_global_seeds
from app.services.career_watch.poll_schedule import fetch_due_companies
from app.services.career_watch.registry import fetch_company_jobs

log = structlog.get_logger("career_watch.poller")


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
    """Fetch jobs for ``company`` and upsert both cache tables. Returns new job count."""
    now = now or datetime.now(timezone.utc)
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

    inserted = await sync_polled_jobs_to_caches(session, company, jobs, now=now)
    company.last_polled_at = now
    company.poll_fail_count = 0
    company.updated_at = now
    await session.flush()
    return inserted


async def _due_companies_global_then_watchlist(
    session: AsyncSession,
    *,
    limit: int,
    now: datetime,
) -> list[WatchedCompany]:
    """Global seeds first, then user-watch due companies, deduped by id."""
    watch_reserve = max(1, limit // 5)
    global_limit = max(1, limit - watch_reserve)
    global_due = await fetch_due_global_seeds(session, limit=global_limit, now=now)
    watch_due = await fetch_due_companies(session, limit=limit, now=now)
    seen: set[uuid.UUID] = set()
    ordered: list[WatchedCompany] = []
    for company in (*global_due, *watch_due):
        if company.id in seen:
            continue
        seen.add(company.id)
        ordered.append(company)
        if len(ordered) >= limit:
            break
    return ordered


async def poll_due_companies(
    session: AsyncSession,
    *,
    limit: int = 50,
    now: datetime | None = None,
) -> PollStats:
    """Poll global seeds first, then user-watch tier due companies."""
    now = now or datetime.now(timezone.utc)
    companies = await _due_companies_global_then_watchlist(
        session, limit=limit, now=now
    )
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
