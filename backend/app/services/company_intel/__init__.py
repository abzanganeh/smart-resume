"""Public API for the company intelligence service.

Usage::

    from app.services.company_intel import get_company_intel

    intel = await get_company_intel(db, company_name="Stripe", jd_text=session.jd_raw)
    if intel and not intel.is_empty():
        session.company_intel = intel

The function:
  1. Normalises the company name to a cache key.
  2. Checks the DB cache (returns immediately on hit within TTL).
  3. Runs cheap-model extraction from JD text on a cache miss.
  4. Writes the result back to cache and commits.

Any failure in extraction or DB I/O is caught here so callers never need
to handle exceptions from this module.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_profile import CompanyIntelOutput
from app.services.company_intel.cache import get_cached, normalise_key, upsert_cache
from app.services.company_intel.extractor import extract_from_jd

log = structlog.get_logger("company_intel")

__all__ = ["get_company_intel"]


async def get_company_intel(
    db: AsyncSession,
    *,
    company_name: str,
    jd_text: str,
) -> CompanyIntelOutput | None:
    """Return company intelligence for ``company_name``, using cache when available.

    Returns None if extraction fails or no platform key is configured.
    The caller is responsible for storing the result on the session object.
    """
    if not company_name or company_name.lower() in {"unknown", "—", ""}:
        return None

    company_key = normalise_key(company_name)

    try:
        cached = await get_cached(db, company_key)
        if cached is not None:
            return cached
    except Exception as exc:
        log.warning("company_intel_cache_read_error", company_key=company_key, error=str(exc))

    intel = await extract_from_jd(company_name, jd_text)
    if intel is None or intel.is_empty():
        return None

    try:
        await upsert_cache(db, company_key, intel)
        await db.commit()
    except Exception as exc:
        log.warning("company_intel_cache_write_error", company_key=company_key, error=str(exc))
        await db.rollback()

    return intel
