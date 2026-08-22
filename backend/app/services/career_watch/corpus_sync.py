"""Sync polled ATS jobs into career_job_cache and job_cache (unified corpus path).

Every successful company poll — global seed or user-initiated watch — upserts the
same public ``job_cache`` rows keyed by ``dedup_key``. User watchlists only
control poll priority via ``UserWatchedCompany``; they never write user ids,
keywords, or per-user source tags into shared search results.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.career_watch import CareerJobCache, WatchedCompany
from app.models.jobs import JobCache
from app.services.career_watch.corpus_privacy import (
    assert_corpus_sources,
    sanitize_parsed_job_for_corpus,
)
from app.services.career_watch.types import ParsedJob
from app.services.jobs.normalization import (
    compute_dedup_key_v2,
    normalize_apply_url,
    normalize_location,
)
from app.services.jobs.cache_writer import upsert_job_cache


def _description_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _job_cache_record_from_poll(
    company: WatchedCompany,
    job: ParsedJob,
    *,
    now: datetime,
) -> dict:
    job = sanitize_parsed_job_for_corpus(job)
    city, country = normalize_location(job.location)
    posted_date = job.posted_at or now
    apply_url_norm = normalize_apply_url(job.apply_url)
    ats_type = company.ats_type.value if company.ats_type else None
    dedup_key = compute_dedup_key_v2(
        apply_url=job.apply_url,
        ats_type=ats_type,
        external_job_id=job.external_job_id,
        company=company.name,
        title=job.title,
        city=city,
        posted_date=posted_date,
    )
    ttl = settings.JOB_CACHE_TTL_UNIQUE_SECONDS
    return {
        "sources": assert_corpus_sources(["corpus"]),
        "external_ids": {ats_type or "corpus": job.external_job_id},
        "title": job.title,
        "company": company.name,
        "company_normalized": company.name.lower(),
        "location": job.location,
        "location_city": city,
        "location_country": country,
        "remote": "remote" in job.location.lower(),
        "salary_min_usd": None,
        "salary_max_usd": None,
        "salary_currency_original": None,
        "employment_type": "",
        "posted_date": posted_date,
        "description": job.description_text,
        "apply_url": job.apply_url,
        "raw_json": job.raw_payload,
        "cached_at": now,
        "expires_at": now + timedelta(seconds=ttl),
        "dedup_key": dedup_key,
        "apply_url_normalized": apply_url_norm,
        "ats_type": ats_type,
        "external_job_id": job.external_job_id,
        "first_seen_at": now,
        "last_seen_at": now,
        "is_active": True,
    }


async def _upsert_career_job_cache(
    session: AsyncSession,
    company: WatchedCompany,
    job: ParsedJob,
    *,
    now: datetime,
) -> bool:
    """Upsert one career_job_cache row. Returns True when newly inserted."""
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
        return True

    existing.title = job.title
    existing.location = job.location
    existing.apply_url = job.apply_url
    existing.description_text = job.description_text
    existing.description_hash = desc_hash
    existing.posted_at = job.posted_at
    existing.last_seen_at = now
    existing.is_open = True
    existing.raw_payload = job.raw_payload
    return False


async def _upsert_job_cache_from_poll(
    session: AsyncSession,
    company: WatchedCompany,
    job: ParsedJob,
    *,
    now: datetime,
) -> None:
    record = _job_cache_record_from_poll(company, job, now=now)
    dedup_key = record["dedup_key"]
    existing = (
        await session.execute(select(JobCache).where(JobCache.dedup_key == dedup_key))
    ).scalar_one_or_none()
    if existing is None:
        await upsert_job_cache(session, record)
        return

    existing.title = record["title"]
    existing.company = record["company"]
    existing.company_normalized = record["company_normalized"]
    existing.location = record["location"]
    existing.location_city = record.get("location_city")
    existing.location_country = record.get("location_country")
    existing.remote = record.get("remote", False)
    existing.posted_date = record["posted_date"]
    existing.description = record.get("description", "")
    existing.apply_url = record.get("apply_url", "")
    existing.raw_json = record.get("raw_json") or {}
    existing.cached_at = now
    existing.expires_at = record["expires_at"]
    existing.apply_url_normalized = record.get("apply_url_normalized")
    existing.ats_type = record.get("ats_type")
    existing.external_job_id = record.get("external_job_id")
    existing.last_seen_at = now
    existing.is_active = True
    if existing.first_seen_at is None:
        existing.first_seen_at = now
    sources = list(existing.sources or [])
    for src in assert_corpus_sources(["corpus"]):
        if src not in sources:
            sources.append(src)
    existing.sources = sources
    await session.flush()


async def tombstone_stale_jobs(
    session: AsyncSession,
    company: WatchedCompany,
    seen_external_ids: set[str],
    *,
    now: datetime | None = None,
) -> int:
    """Mark jobs missing from the latest poll inactive in both caches."""
    now = now or datetime.now(timezone.utc)
    tombstoned = 0
    career_rows = (
        await session.execute(
            select(CareerJobCache)
            .where(CareerJobCache.watched_company_id == company.id)
            .where(CareerJobCache.is_open.is_(True))
        )
    ).scalars().all()
    for row in career_rows:
        if row.external_job_id not in seen_external_ids:
            row.is_open = False
            tombstoned += 1

    ats_type = company.ats_type.value if company.ats_type else None
    job_rows = (
        await session.execute(
            select(JobCache)
            .where(JobCache.is_active.is_(True))
            .where(JobCache.company_normalized == company.name.lower())
            .where(JobCache.ats_type == ats_type)
        )
    ).scalars().all()
    for row in job_rows:
        if row.external_job_id and row.external_job_id not in seen_external_ids:
            row.is_active = False
            row.last_seen_at = now
    await session.flush()
    return tombstoned


async def sync_polled_jobs_to_caches(
    session: AsyncSession,
    company: WatchedCompany,
    jobs: list[ParsedJob],
    *,
    now: datetime | None = None,
) -> int:
    """Upsert polled jobs into both caches and tombstone missing roles."""
    now = now or datetime.now(timezone.utc)
    inserted = 0
    seen: set[str] = set()
    for job in jobs:
        seen.add(job.external_job_id)
        if await _upsert_career_job_cache(session, company, job, now=now):
            inserted += 1
        await _upsert_job_cache_from_poll(session, company, job, now=now)
    await tombstone_stale_jobs(session, company, seen, now=now)
    return inserted


__all__ = [
    "sync_polled_jobs_to_caches",
    "tombstone_stale_jobs",
]
