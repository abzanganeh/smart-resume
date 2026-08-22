"""Sync free job-aggregator feeds into ``job_cache``."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.jobs import JobCache
from app.services.career_watch.types import ParsedJob
from app.services.jobs.cache_writer import upsert_job_cache
from app.services.jobs.normalization import (
    compute_dedup_key_v2,
    normalize_apply_url,
    normalize_location,
)


def _company_name(job: ParsedJob) -> str:
    raw = job.raw_payload.get("company") or job.raw_payload.get("company_name")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return "Unknown"


def _aggregator_record(
    source: str,
    job: ParsedJob,
    *,
    now: datetime,
) -> dict:
    company = _company_name(job)
    city, country = normalize_location(job.location)
    posted_date = job.posted_at or now
    apply_url_norm = normalize_apply_url(job.apply_url)
    dedup_key = compute_dedup_key_v2(
        apply_url=job.apply_url,
        ats_type=f"aggregator_{source}",
        external_job_id=job.external_job_id,
        company=company,
        title=job.title,
        city=city,
        posted_date=posted_date,
    )
    ttl = settings.JOB_CACHE_TTL_UNIQUE_SECONDS
    return {
        "sources": ["corpus", f"aggregator:{source}"],
        "external_ids": {source: job.external_job_id},
        "title": job.title,
        "company": company,
        "company_normalized": company.lower(),
        "location": job.location,
        "location_city": city,
        "location_country": country,
        "remote": "remote" in job.location.lower() or bool(job.raw_payload.get("remote")),
        "salary_min_usd": None,
        "salary_max_usd": None,
        "salary_currency_original": None,
        "employment_type": str(job.raw_payload.get("job_type") or ""),
        "posted_date": posted_date,
        "description": job.description_text,
        "apply_url": job.apply_url,
        "raw_json": job.raw_payload,
        "cached_at": now,
        "expires_at": now + timedelta(seconds=ttl),
        "dedup_key": dedup_key,
        "apply_url_normalized": apply_url_norm,
        "ats_type": f"aggregator_{source}",
        "external_job_id": job.external_job_id,
        "first_seen_at": now,
        "last_seen_at": now,
        "is_active": True,
    }


async def sync_aggregator_jobs_to_cache(
    session: AsyncSession,
    *,
    source: str,
    jobs: list[ParsedJob],
    now: datetime | None = None,
) -> int:
    """Upsert aggregator rows into shared ``job_cache`` (no career watch company row)."""
    now = now or datetime.now(timezone.utc)
    upserted = 0
    for job in jobs:
        record = _aggregator_record(source, job, now=now)
        dedup_key = record["dedup_key"]
        existing = (
            await session.execute(select(JobCache).where(JobCache.dedup_key == dedup_key))
        ).scalar_one_or_none()
        if existing is None:
            await upsert_job_cache(session, record)
            upserted += 1
            continue
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
        for src in record["sources"]:
            if src not in sources:
                sources.append(src)
        existing.sources = sources
        await session.flush()
    return upserted


def stable_external_id(source: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return f"{source}-{digest[:24]}"


__all__ = ["stable_external_id", "sync_aggregator_jobs_to_cache"]
