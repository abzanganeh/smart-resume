"""AuthAuditLog writes + login-failure lockout detection.

§18.2: "5 failed logins in 15 min → temporary lockout + 'suspicious
login' email."  We implement that purely as DB queries against
``auth_audit_log`` so the rule survives process restarts and is
auditable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import AuthAuditEvent, AuthAuditLog

log = structlog.get_logger("auth.audit")


async def record_auth_event(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    event: AuthAuditEvent,
    ip: str,
    user_agent: str,
    metadata: dict[str, Any] | None = None,
) -> AuthAuditLog:
    """Insert a row into ``auth_audit_log`` and flush.

    Never raises; if the DB rejects the write we log and swallow so the
    surrounding business action (e.g. successful login) is not dropped
    on the floor for a logging failure.
    """
    row = AuthAuditLog(
        id=uuid.uuid4(),
        user_id=user_id,
        event=event,
        ip=(ip or "")[:64],
        user_agent=(user_agent or "")[:512],
        event_metadata=metadata or {},
        created_at=datetime.now(timezone.utc),
    )
    try:
        session.add(row)
        await session.flush()
    except Exception as exc:  # pragma: no cover - DB outage path
        log.warning("auth.audit.write_failed", error=str(exc), event=event.value)
    return row


async def recent_login_failure_count(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    window_seconds: int | None = None,
) -> int:
    """Count login_failure rows for ``user_id`` inside the lockout window."""
    window = window_seconds or settings.LOGIN_FAILURE_WINDOW_SECONDS
    since = datetime.now(timezone.utc) - timedelta(seconds=window)
    stmt = (
        select(func.count())
        .select_from(AuthAuditLog)
        .where(
            AuthAuditLog.user_id == user_id,
            AuthAuditLog.event == AuthAuditEvent.login_failure,
            AuthAuditLog.created_at >= since,
        )
    )
    return int((await session.execute(stmt)).scalar() or 0)


async def is_account_locked(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    threshold: int | None = None,
    window_seconds: int | None = None,
) -> bool:
    """Return True if ``user_id`` has hit the failure threshold in-window."""
    limit = threshold or settings.LOGIN_FAILURE_LOCKOUT_THRESHOLD
    return await recent_login_failure_count(
        session, user_id=user_id, window_seconds=window_seconds
    ) >= limit


__all__ = [
    "is_account_locked",
    "recent_login_failure_count",
    "record_auth_event",
]
