"""Daily signup rate limits keyed on IP and (IP, device fingerprint)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User


class SignupRateLimitError(Exception):
    """Signup refused because a daily network limit was exceeded."""


async def _count_signups(
    session: AsyncSession,
    *,
    since: datetime,
    signup_ip: str,
    device_fingerprint_hash: str | None = None,
) -> int:
    stmt = (
        select(func.count())
        .select_from(User)
        .where(User.created_at >= since)
        .where(User.signup_ip == signup_ip)
    )
    if device_fingerprint_hash is not None:
        stmt = stmt.where(User.signup_device_fingerprint_hash == device_fingerprint_hash)
    return int((await session.execute(stmt)).scalar() or 0)


async def fingerprint_usable_for_narrow_limit(
    session: AsyncSession,
    *,
    signup_ip: str,
    device_fingerprint_hash: str | None,
    since: datetime,
) -> bool:
    if not device_fingerprint_hash:
        return False
    collisions = await _count_signups(
        session,
        since=since,
        signup_ip=signup_ip,
        device_fingerprint_hash=device_fingerprint_hash,
    )
    return collisions < settings.SIGNUP_FINGERPRINT_COLLISION_THRESHOLD


async def assert_signup_rate_limit_allowed(
    session: AsyncSession,
    *,
    signup_ip: str,
    device_fingerprint_hash: str | None,
    now: datetime | None = None,
) -> None:
    """Raise ``SignupRateLimitError`` when daily signup caps are exceeded."""
    if not signup_ip:
        return

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=1)

    ip_count = await _count_signups(session, since=since, signup_ip=signup_ip)
    if ip_count >= settings.SIGNUP_IP_DAILY_LIMIT:
        raise SignupRateLimitError("signup_ip_daily_limit")

    if await fingerprint_usable_for_narrow_limit(
        session,
        signup_ip=signup_ip,
        device_fingerprint_hash=device_fingerprint_hash,
        since=since,
    ):
        narrow_count = await _count_signups(
            session,
            since=since,
            signup_ip=signup_ip,
            device_fingerprint_hash=device_fingerprint_hash,
        )
        if narrow_count >= settings.SIGNUP_IP_DEVICE_DAILY_LIMIT:
            raise SignupRateLimitError("signup_ip_device_daily_limit")


__all__ = [
    "SignupRateLimitError",
    "assert_signup_rate_limit_allowed",
    "fingerprint_usable_for_narrow_limit",
]
