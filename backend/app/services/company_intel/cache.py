"""DB cache read/write for company intelligence profiles.

Cache key is a normalised slug of the company name so all JDs from the
same employer share one row.  TTL is evaluated at read time; stale rows
are overwritten on the next successful extraction rather than deleted by a
background job.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.company_profile import CompanyIntelOutput, CompanyProfile

log = structlog.get_logger("company_intel.cache")

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalise_key(company_name: str) -> str:
    """Return a stable slug usable as a cache key.

    >>> normalise_key("Google LLC")
    'google-llc'
    >>> normalise_key("Amazon Web Services (AWS)")
    'amazon-web-services-aws'
    """
    slug = company_name.strip().lower()
    slug = _NON_ALNUM.sub("-", slug).strip("-")
    return slug[:200] or "unknown"


def _is_stale(cached_at: datetime) -> bool:
    ttl = timedelta(days=settings.COMPANY_INTEL_CACHE_DAYS)
    # asyncpg returns tz-aware datetimes for TIMESTAMPTZ columns; guard against
    # naive values coming from tests or a different driver.
    aware = cached_at if cached_at.tzinfo is not None else cached_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - aware > ttl


async def get_cached(db: AsyncSession, company_key: str) -> CompanyIntelOutput | None:
    """Return cached intel if present and within TTL, else None."""
    row: CompanyProfile | None = (
        await db.execute(
            select(CompanyProfile).where(CompanyProfile.company_key == company_key)
        )
    ).scalar_one_or_none()

    if row is None:
        return None

    if _is_stale(row.cached_at):
        log.info("company_intel_cache_stale", company_key=company_key)
        return None

    log.info("company_intel_cache_hit", company_key=company_key)
    return CompanyIntelOutput(
        company_name=row.company_name,
        mission=row.mission,
        values=list(row.values or []),
        culture_notes=row.culture_notes,
        source="cache",
    )


async def upsert_cache(
    db: AsyncSession,
    company_key: str,
    intel: CompanyIntelOutput,
) -> None:
    """Insert or update the cache row for ``company_key``.

    Uses Postgres ``ON CONFLICT DO UPDATE`` so concurrent upserts on the
    same key are safe.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(CompanyProfile)
        .values(
            company_key=company_key,
            company_name=intel.company_name,
            mission=intel.mission,
            values=intel.values,
            culture_notes=intel.culture_notes,
            cached_at=now,
        )
        .on_conflict_do_update(
            index_elements=["company_key"],
            set_={
                "company_name": intel.company_name,
                "mission": intel.mission,
                "values": intel.values,
                "culture_notes": intel.culture_notes,
                "cached_at": now,
            },
        )
    )
    await db.execute(stmt)
    log.info("company_intel_cache_write", company_key=company_key)
