"""Background helpers that operate against the identity surface.

Currently a single job — ``soft_delete_unverified_accounts`` — which
implements §18.2: "Unverified accounts older than 7 days are soft-deleted
by a daily cron job."

The function is written so it can be invoked either from a CLI worker
(see ``scripts/`` in later steps) or from an in-process scheduler hook.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import AuthProvider, User

log = structlog.get_logger("auth.maintenance")


@dataclass(frozen=True, slots=True)
class CleanupResult:
    inspected: int
    suspended: list[str]
    dry_run: bool = False


async def soft_delete_unverified_accounts(
    session: AsyncSession,
    *,
    older_than: timedelta | None = None,
    now: datetime | None = None,
    dry_run: bool | None = None,
) -> CleanupResult:
    """Mark unverified email-based accounts older than ``older_than`` as suspended.

    We use ``suspended_at`` rather than hard deletion so users still have
    a 30-day window (via account-closure restoration) to recover.  The
    hard delete is performed by §19.6 closure flow on day 30.

    Only accounts created via ``auth_provider="email"`` are eligible —
    OAuth signups are considered verified by the provider.

    When ``dry_run`` is true, eligible accounts are counted and returned
    but not modified — use this for the first scheduled deploy.
    """
    cutoff_now = now or datetime.now(timezone.utc)
    window_days = settings.UNVERIFIED_ACCOUNT_CLEANUP_DAYS
    older_than = older_than or timedelta(days=window_days)
    dry_run = (
        settings.UNVERIFIED_ACCOUNT_CLEANUP_DRY_RUN
        if dry_run is None
        else dry_run
    )
    cutoff = cutoff_now - older_than

    stmt = (
        select(User)
        .where(User.email_verified_at.is_(None))
        .where(User.auth_provider == AuthProvider.email)
        .where(User.suspended_at.is_(None))
        .where(User.created_at < cutoff)
    )
    rows: Iterable[User] = (await session.execute(stmt)).scalars().all()
    suspended_ids: list[str] = []
    for user in rows:
        suspended_ids.append(str(user.id))
        if dry_run:
            continue
        user.suspended_at = cutoff_now
        user.suspension_reason = "email_not_verified_7d"

    if suspended_ids and not dry_run:
        await session.flush()
        log.info(
            "auth.maintenance.unverified_suspended",
            count=len(suspended_ids),
            cutoff=cutoff.isoformat(),
        )
    elif suspended_ids and dry_run:
        log.info(
            "auth.maintenance.unverified_dry_run",
            count=len(suspended_ids),
            cutoff=cutoff.isoformat(),
        )

    return CleanupResult(
        inspected=len(suspended_ids),
        suspended=suspended_ids,
        dry_run=dry_run,
    )


async def run_unverified_cleanup_tick(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    dry_run: bool | None = None,
) -> CleanupResult:
    """Scheduler entrypoint for daily unverified-account cleanup."""
    return await soft_delete_unverified_accounts(
        session,
        now=now,
        dry_run=dry_run,
    )


__all__ = [
    "CleanupResult",
    "run_unverified_cleanup_tick",
    "soft_delete_unverified_accounts",
]
