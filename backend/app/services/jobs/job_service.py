"""Job search orchestration — cache, Hirebase, logging, persistence."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.jobs import JobCache, JobSearchLog, JobSearchSource, SavedJob
from app.models.master_resume import MasterResume
from app.services.jobs.cache_writer import normalize_apify_record, upsert_job_cache
from app.services.jobs.circuit_breaker import (
    HirebaseUnavailableError,
    get_circuit_state,
)
from app.services.jobs.filtering import filter_blocked_companies
from app.services.jobs import hirebase_client
from app.services.jobs.schemas import JobResult

log = structlog.get_logger("jobs.service")

_STALE_MESSAGE = (
    "Job search is temporarily unavailable. Showing cached results that may not be "
    "fully up to date."
)
_OUTAGE_EMPTY_MESSAGE = (
    "Job search is temporarily unavailable and we have no cached results for this query. "
    "Please try again in a few minutes."
)


def normalize_query(query: str) -> str:
    """Collapse whitespace and strip decorative punctuation."""
    text = re.sub(r"\s+", " ", query.strip())
    return text[:500]


def job_cache_to_result(row: JobCache, *, score: float | None = None) -> JobResult:
    return JobResult(
        id=row.id,
        title=row.title,
        company=row.company,
        location=row.location,
        remote=row.remote,
        salary_min_usd=row.salary_min_usd,
        salary_max_usd=row.salary_max_usd,
        employment_type=row.employment_type,
        posted_date=row.posted_date,
        description=row.description,
        apply_url=row.apply_url,
        sources=list(row.sources or []),
        score=score,
        first_seen_at=row.first_seen_at,
    )


async def hirebase_results_to_jobs(
    mapped: list[dict[str, Any]],
    *,
    session: AsyncSession,
    source: str,
) -> list[JobResult]:
    """Upsert Hirebase rows into ``job_cache`` and return :class:`JobResult` list."""
    ttl = settings.JOB_CACHE_TTL_COMMON_SECONDS
    results: list[JobResult] = []
    for item in mapped:
        record = normalize_apify_record(
            {
                "company": item.get("company"),
                "title": item.get("title"),
                "location": item.get("location"),
                "remote": item.get("remote"),
                "salary_min": item.get("salary_min"),
                "salary_max": item.get("salary_max"),
                "salary_currency": item.get("salary_currency"),
                "employment_type": item.get("employment_type"),
                "postedDate": item.get("posted_date"),
                "description": item.get("description"),
                "url": item.get("apply_url"),
                "id": item.get("id"),
            },
            source=source,
            ttl_seconds=ttl,
        )
        row = await upsert_job_cache(session, record)
        results.append(
            job_cache_to_result(row, score=item.get("score"))
        )
    return results


async def search_active_job_cache(
    session: AsyncSession,
    *,
    query: str,
    location: str | None,
    filters: dict[str, Any],
    page: int,
    page_size: int,
    blocked_companies: list[str],
) -> tuple[list[JobResult], int]:
    """Search active corpus rows in ``job_cache`` (DB-first path)."""
    now = datetime.now(timezone.utc)
    terms = [t for t in query.lower().split() if len(t) > 2]
    stmt = (
        select(JobCache)
        .where(JobCache.is_active.is_(True))
        .where(
            (JobCache.expires_at > now)
            | JobCache.sources.contains(["corpus"])
        )
    )
    if terms:
        clauses = [
            or_(
                JobCache.title.ilike(f"%{term}%"),
                JobCache.company.ilike(f"%{term}%"),
                JobCache.description.ilike(f"%{term}%"),
            )
            for term in terms[:6]
        ]
        stmt = stmt.where(or_(*clauses))
    if location and location.strip():
        loc = f"%{location.strip()}%"
        stmt = stmt.where(JobCache.location.ilike(loc))
    if filters.get("remote"):
        stmt = stmt.where(JobCache.remote.is_(True))

    offset = (page - 1) * page_size
    count_stmt = stmt.with_only_columns(func.count()).order_by(None)
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = (
        await session.execute(
            stmt.order_by(
                JobCache.first_seen_at.desc().nullslast(),
                JobCache.posted_date.desc(),
            )
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()

    jobs = filter_blocked_companies(
        [job_cache_to_result(r) for r in rows],
        blocked_companies,
    )
    return jobs, total


async def search_cache(
    session: AsyncSession,
    *,
    query: str,
    location: str | None,
    filters: dict[str, Any],
    page: int,
    page_size: int,
    blocked_companies: list[str],
) -> tuple[list[JobResult], int]:
    """Search non-expired ``job_cache`` rows (circuit-open fallback)."""
    now = datetime.now(timezone.utc)
    terms = [t for t in query.lower().split() if len(t) > 2]
    stmt = select(JobCache).where(JobCache.expires_at > now)
    if terms:
        clauses = [
            or_(
                JobCache.title.ilike(f"%{term}%"),
                JobCache.company.ilike(f"%{term}%"),
                JobCache.description.ilike(f"%{term}%"),
            )
            for term in terms[:6]
        ]
        stmt = stmt.where(or_(*clauses))
    if location and location.strip():
        loc = f"%{location.strip()}%"
        stmt = stmt.where(JobCache.location.ilike(loc))
    if filters.get("remote"):
        stmt = stmt.where(JobCache.remote.is_(True))

    offset = (page - 1) * page_size
    rows = (
        await session.execute(
            stmt.order_by(JobCache.posted_date.desc()).offset(offset).limit(page_size)
        )
    ).scalars().all()

    jobs = filter_blocked_companies(
        [job_cache_to_result(r) for r in rows],
        blocked_companies,
    )
    return jobs, len(jobs)


async def get_job_by_id(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> JobCache | None:
    return (
        await session.execute(select(JobCache).where(JobCache.id == job_id))
    ).scalar_one_or_none()


async def log_search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    location: str | None,
    filters: dict[str, Any],
    result_count: int,
    source: JobSearchSource,
    cost_usd: float = 0.0,
) -> None:
    session.add(
        JobSearchLog(
            id=uuid.uuid4(),
            user_id=user_id,
            query=query,
            location=location,
            filters=filters,
            result_count=result_count,
            source=source,
            cost_usd=cost_usd,
        )
    )
    await session.flush()


async def run_keyword_search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    location: str | None,
    filters: dict[str, Any],
    page: int,
    page_size: int,
    blocked_companies: list[str],
    expand: bool = False,
) -> tuple[list[JobResult], int, bool, str | None, bool, str]:
    """Execute search; returns (jobs, total, stale, message, charge_quota, source)."""
    normalized = normalize_query(query)
    circuit = await get_circuit_state()
    corpus_jobs: list[JobResult] = []
    corpus_total = 0
    min_results = settings.JOB_SEARCH_DB_MIN_RESULTS

    if settings.JOB_SEARCH_DB_FIRST:
        corpus_jobs, corpus_total = await search_active_job_cache(
            session,
            query=normalized,
            location=location,
            filters=filters,
            page=page,
            page_size=page_size,
            blocked_companies=blocked_companies,
        )
        if corpus_total >= min_results and not expand:
            await log_search(
                session,
                user_id=user_id,
                query=normalized,
                location=location,
                filters=filters,
                result_count=corpus_total,
                source=JobSearchSource.cache,
            )
            return corpus_jobs, corpus_total, False, None, False, "corpus"

    if circuit.is_open:
        jobs, total = await search_active_job_cache(
            session,
            query=normalized,
            location=location,
            filters=filters,
            page=page,
            page_size=page_size,
            blocked_companies=blocked_companies,
        )
        if not jobs:
            jobs, total = await search_cache(
                session,
                query=normalized,
                location=location,
                filters=filters,
                page=page,
                page_size=page_size,
                blocked_companies=blocked_companies,
            )
        if jobs:
            await log_search(
                session,
                user_id=user_id,
                query=normalized,
                location=location,
                filters=filters,
                result_count=len(jobs),
                source=JobSearchSource.cache,
            )
            return jobs, total, True, _STALE_MESSAGE, False, "corpus"
        await log_search(
            session,
            user_id=user_id,
            query=normalized,
            location=location,
            filters=filters,
            result_count=0,
            source=JobSearchSource.cache,
        )
        return [], 0, True, _OUTAGE_EMPTY_MESSAGE, False, "corpus"

    try:
        mapped = await hirebase_client.search(
            normalized,
            location,
            filters,
            page,
            page_size=page_size,
        )
        raw_jobs = await hirebase_results_to_jobs(
            mapped, session=session, source="hirebase"
        )
    except HirebaseUnavailableError:
        jobs, total = await search_active_job_cache(
            session,
            query=normalized,
            location=location,
            filters=filters,
            page=page,
            page_size=page_size,
            blocked_companies=blocked_companies,
        )
        if not jobs:
            jobs, total = await search_cache(
                session,
                query=normalized,
                location=location,
                filters=filters,
                page=page,
                page_size=page_size,
                blocked_companies=blocked_companies,
            )
        if jobs:
            await log_search(
                session,
                user_id=user_id,
                query=normalized,
                location=location,
                filters=filters,
                result_count=len(jobs),
                source=JobSearchSource.cache,
            )
            return jobs, total, True, _STALE_MESSAGE, False, "corpus"
        await log_search(
            session,
            user_id=user_id,
            query=normalized,
            location=location,
            filters=filters,
            result_count=0,
            source=JobSearchSource.cache,
        )
        return [], 0, True, _OUTAGE_EMPTY_MESSAGE, False, "corpus"
    except hirebase_client.HirebaseClientError as exc:
        log.warning("hirebase.search_failed", error=str(exc))
        jobs, total = await search_active_job_cache(
            session,
            query=normalized,
            location=location,
            filters=filters,
            page=page,
            page_size=page_size,
            blocked_companies=blocked_companies,
        )
        if not jobs:
            jobs, total = await search_cache(
                session,
                query=normalized,
                location=location,
                filters=filters,
                page=page,
                page_size=page_size,
                blocked_companies=blocked_companies,
            )
        if jobs:
            await log_search(
                session,
                user_id=user_id,
                query=normalized,
                location=location,
                filters=filters,
                result_count=len(jobs),
                source=JobSearchSource.cache,
            )
            return jobs, total, True, _STALE_MESSAGE, False, "corpus"
        await log_search(
            session,
            user_id=user_id,
            query=normalized,
            location=location,
            filters=filters,
            result_count=0,
            source=JobSearchSource.cache,
        )
        return [], 0, True, _OUTAGE_EMPTY_MESSAGE, False, "corpus"

    hirebase_jobs = filter_blocked_companies(raw_jobs, blocked_companies)
    if settings.JOB_SEARCH_DB_FIRST and (expand or corpus_total < min_results):
        seen_keys: set[str] = set()
        for job in corpus_jobs:
            key = job.apply_url.rstrip("/").lower() if job.apply_url else str(job.id)
            seen_keys.add(key)
        merged = list(corpus_jobs)
        for job in hirebase_jobs:
            key = job.apply_url.rstrip("/").lower() if job.apply_url else str(job.id)
            if key in seen_keys:
                continue
            merged.append(job)
            seen_keys.add(key)
        await log_search(
            session,
            user_id=user_id,
            query=normalized,
            location=location,
            filters=filters,
            result_count=len(merged),
            source=JobSearchSource.hirebase,
        )
        source = "corpus+hirebase" if corpus_jobs else "hirebase"
        return merged, len(merged), False, None, True, source

    await log_search(
        session,
        user_id=user_id,
        query=normalized,
        location=location,
        filters=filters,
        result_count=len(hirebase_jobs),
        source=JobSearchSource.hirebase,
    )
    return hirebase_jobs, len(hirebase_jobs), False, None, True, "hirebase"


async def run_resume_match(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    page: int,
    page_size: int,
    blocked_companies: list[str],
) -> tuple[list[JobResult], int, bool, str | None, bool]:
    """Match jobs to the user's master resume via Hirebase artifact."""
    master = (
        await session.execute(
            select(MasterResume).where(MasterResume.user_id == user_id)
        )
    ).scalar_one_or_none()
    if master is None or not master.raw_text.strip():
        return [], 0, False, "Upload a master resume on /profile first.", False

    artifact_id = master.hirebase_artifact_id
    if not artifact_id:
        artifact_id = await hirebase_client.embed_resume(master.raw_text)
        master.hirebase_artifact_id = artifact_id
        await session.flush()

    circuit = await get_circuit_state()
    if circuit.is_open:
        jobs, total = await search_cache(
            session,
            query=master.raw_text[:200],
            location=None,
            filters={},
            page=page,
            page_size=page_size,
            blocked_companies=blocked_companies,
        )
        if jobs:
            return jobs, total, True, _STALE_MESSAGE, False
        return [], 0, True, _OUTAGE_EMPTY_MESSAGE, False

    try:
        mapped = await hirebase_client.match_resume(
            artifact_id, page, page_size=page_size
        )
        raw_jobs = await hirebase_results_to_jobs(
            mapped, session=session, source="hirebase"
        )
    except (HirebaseUnavailableError, hirebase_client.HirebaseClientError):
        jobs, total = await search_cache(
            session,
            query=master.raw_text[:200],
            location=None,
            filters={},
            page=page,
            page_size=page_size,
            blocked_companies=blocked_companies,
        )
        if jobs:
            return jobs, total, True, _STALE_MESSAGE, False
        return [], 0, True, _OUTAGE_EMPTY_MESSAGE, False

    jobs = filter_blocked_companies(raw_jobs, blocked_companies)
    return jobs, len(jobs), False, None, True


async def list_saved_jobs(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    blocked_companies: list[str],
) -> list[JobResult]:
    rows = (
        await session.execute(
            select(JobCache)
            .join(SavedJob, SavedJob.job_cache_id == JobCache.id)
            .where(SavedJob.user_id == user_id)
            .order_by(SavedJob.created_at.desc())
        )
    ).scalars().all()
    return filter_blocked_companies(
        [job_cache_to_result(r) for r in rows],
        blocked_companies,
    )


__all__ = [
    "get_job_by_id",
    "hirebase_results_to_jobs",
    "list_saved_jobs",
    "log_search",
    "normalize_query",
    "run_keyword_search",
    "run_resume_match",
    "search_active_job_cache",
    "search_cache",
]
