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

from app.config import settings
from app.models.company_profile import CompanyIntelOutput
from app.models.session import Session
from app.services.company_intel.cache import get_cached, normalise_key, upsert_cache
from app.services.company_intel.extractor import extract_from_jd
from app.services.dashboard.resume_record import resolve_company_name

log = structlog.get_logger("company_intel")

__all__ = ["get_company_intel", "ensure_session_company_intel"]


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
    if not (jd_text or "").strip():
        return None
    if not settings.DATABASE_URL.strip():
        log.info("company_intel_skipped_no_database")
        return None

    company_key = normalise_key(company_name)
    if company_key == "unknown":
        return None

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


async def ensure_session_company_intel(session: Session) -> None:
    """Load company intel when missing; mutates ``session.company_intel`` in place."""
    if session.company_intel is not None and not session.company_intel.is_empty():
        return

    jd_text = session.jd_raw or ""
    if not jd_text.strip():
        return

    company_name = resolve_company_name(session)
    if not company_name or company_name == "Unknown":
        return

    try:
        from app.db.engine import async_session_factory

        async with async_session_factory() as db:
            intel = await get_company_intel(
                db,
                company_name=company_name,
                jd_text=jd_text,
            )
    except Exception as exc:
        log.warning("company_intel_session_fetch_failed", error=str(exc))
        return

    if intel is None or intel.is_empty():
        return

    session.company_intel = intel
    log.info(
        "company_intel_session_loaded",
        company=company_name,
        source=intel.source,
    )

    try:
        from app.services import session_store as _store

        await _store.update_session(session)
    except Exception as exc:
        log.warning("company_intel_session_persist_failed", error=str(exc))
