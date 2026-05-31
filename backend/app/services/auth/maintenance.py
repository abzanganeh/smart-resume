"""Background helpers that operate against the identity surface.

Currently a single job — ``soft_delete_unverified_accounts`` — which
implements §18.2: "Unverified accounts older than 7 days are soft-deleted
by a daily cron job."

The function is written so it can be invoked either from a CLI worker
(see ``scripts/`` in later steps) or from an in-process scheduler hook.
A future ``CronWorker`` (Step 31) will wire it up; until then the
function is callable directly and covered by an integration test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AuthProvider, User

log = structlog.get_logger("auth.maintenance")


@dataclass(frozen=True, slots=True)
class CleanupResult:
    inspected: int
    suspended: list[str]


async def soft_delete_unverified_accounts(
    session: AsyncSession,
    *,
    older_than: timedelta = timedelta(days=7),
    now: datetime | None = None,
) -> CleanupResult:
    """Mark unverified email-based accounts older than ``older_than`` as suspended.

    We use ``suspended_at`` rather than hard deletion so users still have
    a 30-day window (via account-closure restoration) to recover.  The
    hard delete is performed by §19.6 closure flow on day 30.

    Only accounts created via ``auth_provider="email"`` are eligible —
    OAuth signups are considered verified by the provider.
    """
    cutoff_now = now or datetime.now(timezone.utc)
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
        user.suspended_at = cutoff_now
        user.suspension_reason = "email_not_verified_7d"
        suspended_ids.append(str(user.id))

    if suspended_ids:
        await session.flush()
        log.info(
            "auth.maintenance.unverified_suspended",
            count=len(suspended_ids),
            cutoff=cutoff.isoformat(),
        )

    return CleanupResult(inspected=len(suspended_ids), suspended=suspended_ids)


__all__ = ["CleanupResult", "soft_delete_unverified_accounts"]
