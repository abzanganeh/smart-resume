"""Post-signup link analysis for repeat fingerprint / IP clusters."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.auth.signup_rate_limit import fingerprint_usable_for_narrow_limit

FINGERPRINT_REVIEW_THRESHOLD = 3
IP_REVIEW_THRESHOLD = 10


async def _count_recent_signups(
    session: AsyncSession,
    *,
    since: datetime,
    signup_ip: str | None = None,
    device_fingerprint_hash: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(User).where(User.created_at >= since)
    if signup_ip:
        stmt = stmt.where(User.signup_ip == signup_ip)
    if device_fingerprint_hash:
        stmt = stmt.where(User.signup_device_fingerprint_hash == device_fingerprint_hash)
    return int((await session.execute(stmt)).scalar() or 0)


async def analyze_signup_links(
    session: AsyncSession,
    *,
    signup_ip: str | None,
    device_fingerprint_hash: str | None,
    now: datetime | None = None,
) -> str | None:
    """Return an abuse-review flag label or ``None`` when no signal fires."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    if device_fingerprint_hash and signup_ip:
        if await fingerprint_usable_for_narrow_limit(
            session,
            signup_ip=signup_ip,
            device_fingerprint_hash=device_fingerprint_hash,
            since=since,
        ):
            fp_count = await _count_recent_signups(
                session,
                since=since,
                device_fingerprint_hash=device_fingerprint_hash,
            )
            if fp_count >= FINGERPRINT_REVIEW_THRESHOLD:
                return "fingerprint_cluster"

    if signup_ip:
        ip_count = await _count_recent_signups(
            session,
            since=since,
            signup_ip=signup_ip,
        )
        if ip_count >= IP_REVIEW_THRESHOLD:
            return "ip_cluster"

    return None


__all__ = ["analyze_signup_links"]
