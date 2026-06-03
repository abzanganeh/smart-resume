"""Persist normalized job records into ``job_cache`` with dedup upsert."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jobs import JobCache
from app.services.jobs.normalization import (
    compute_dedup_key,
    normalize_location,
    normalize_salary,
)

log = logging.getLogger(__name__)


def _merge_sources(existing: list[str], incoming: str) -> list[str]:
    merged = list(existing or [])
    if incoming and incoming not in merged:
        merged.append(incoming)
    return merged


def _merge_external_ids(
    existing: dict[str, str], incoming: dict[str, str]
) -> dict[str, str]:
    merged = dict(existing or {})
    merged.update(incoming or {})
    return merged


def normalize_apify_record(
    raw: dict[str, Any],
    *,
    source: str = "apify",
    ttl_seconds: int = 3600,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Map a raw Apify/Hirebase job dict into ``job_cache`` column values."""
    now = now or datetime.now(timezone.utc)
    company = str(raw.get("company") or raw.get("companyName") or "")
    title = str(raw.get("title") or raw.get("jobTitle") or "")
    location = str(raw.get("location") or raw.get("locationName") or "")

    city, country = normalize_location(location)
    posted_raw = raw.get("posted_date") or raw.get("postedDate") or raw.get("datePosted")
    if isinstance(posted_raw, str):
        posted_date = datetime.fromisoformat(posted_raw.replace("Z", "+00:00"))
    elif isinstance(posted_raw, datetime):
        posted_date = posted_raw
    else:
        log.warning("missing or unrecognised posted_date in raw record; defaulting to now")
        posted_date = now

    currency = raw.get("salary_currency") or raw.get("salaryCurrency")
    salary_min = normalize_salary(raw.get("salary_min") or raw.get("salaryMin"), currency)
    salary_max = normalize_salary(raw.get("salary_max") or raw.get("salaryMax"), currency)

    external_id = str(raw.get("id") or raw.get("jobId") or "")
    dedup_key = compute_dedup_key(company, title, city, posted_date)

    return {
        "sources": [source],
        "external_ids": {source: external_id} if external_id else {},
        "title": title,
        "company": company,
        "company_normalized": company.lower(),
        "location": location,
        "location_city": city,
        "location_country": country,
        "remote": bool(raw.get("remote") or raw.get("isRemote")),
        "salary_min_usd": salary_min,
        "salary_max_usd": salary_max,
        "salary_currency_original": currency,
        "employment_type": str(raw.get("employment_type") or raw.get("employmentType") or ""),
        "posted_date": posted_date,
        "description": str(raw.get("description") or ""),
        "apply_url": str(raw.get("apply_url") or raw.get("url") or raw.get("link") or ""),
        "raw_json": raw,
        "cached_at": now,
        "expires_at": now + timedelta(seconds=ttl_seconds),
        "dedup_key": dedup_key,
    }


async def upsert_job_cache(
    session: AsyncSession,
    record: dict[str, Any],
) -> JobCache:
    """Insert or update a ``job_cache`` row keyed by ``dedup_key``."""
    dedup_key = record["dedup_key"]
    existing = (
        await session.execute(
            select(JobCache).where(JobCache.dedup_key == dedup_key)
        )
    ).scalar_one_or_none()

    if existing is None:
        row = JobCache(id=uuid.uuid4(), **record)
        session.add(row)
        await session.flush()
        return row

    incoming_source = (record.get("sources") or [""])[0]
    existing.sources = _merge_sources(existing.sources, incoming_source)
    existing.external_ids = _merge_external_ids(
        existing.external_ids, record.get("external_ids") or {}
    )
    existing.title = record["title"]
    existing.company = record["company"]
    existing.company_normalized = record["company_normalized"]
    existing.location = record["location"]
    existing.location_city = record.get("location_city")
    existing.location_country = record.get("location_country")
    existing.remote = record.get("remote", False)
    existing.salary_min_usd = record.get("salary_min_usd")
    existing.salary_max_usd = record.get("salary_max_usd")
    existing.salary_currency_original = record.get("salary_currency_original")
    existing.employment_type = record.get("employment_type", "")
    existing.posted_date = record["posted_date"]
    existing.description = record.get("description", "")
    existing.apply_url = record.get("apply_url", "")
    existing.raw_json = record.get("raw_json") or {}
    existing.cached_at = record.get("cached_at") or existing.cached_at
    existing.expires_at = record["expires_at"]
    await session.flush()
    return existing


__all__ = ["normalize_apify_record", "upsert_job_cache"]
