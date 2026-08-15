"""Runtime lookup for admin ``feature_unlock`` grants."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_grant import AdminGrantType, AdminUserGrant

SUPPORTED_FEATURE_UNLOCKS: frozenset[str] = frozenset(
    {
        "whisper",
        "career_watch",
        "job_search",
        "fit_analysis",
    }
)


def normalize_feature_name(feature: str) -> str:
    return feature.strip().lower()


def is_supported_feature_unlock(feature: str) -> bool:
    return normalize_feature_name(feature) in SUPPORTED_FEATURE_UNLOCKS


async def active_feature_unlocks_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    now: datetime | None = None,
) -> set[str]:
    """Return active unlocked feature names for ``user_id``."""
    now_dt = now or datetime.now(timezone.utc)
    rows = (
        await session.execute(
            select(AdminUserGrant)
            .where(AdminUserGrant.user_id == user_id)
            .where(AdminUserGrant.grant_type == AdminGrantType.feature_unlock)
            .where(AdminUserGrant.revoked_at.is_(None))
        )
    ).scalars().all()

    unlocked: set[str] = set()
    for grant in rows:
        if grant.expires_at is not None and grant.expires_at <= now_dt:
            continue
        feature = grant.payload.get("feature")
        if not isinstance(feature, str):
            continue
        name = normalize_feature_name(feature)
        if name in SUPPORTED_FEATURE_UNLOCKS:
            unlocked.add(name)
    return unlocked


async def user_has_feature_unlock(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    feature: str,
    now: datetime | None = None,
) -> bool:
    name = normalize_feature_name(feature)
    if name not in SUPPORTED_FEATURE_UNLOCKS:
        return False
    unlocked = await active_feature_unlocks_for_user(
        session, user_id=user_id, now=now
    )
    return name in unlocked


__all__ = [
    "SUPPORTED_FEATURE_UNLOCKS",
    "active_feature_unlocks_for_user",
    "is_supported_feature_unlock",
    "normalize_feature_name",
    "user_has_feature_unlock",
]
