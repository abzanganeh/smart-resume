"""Admin audit log helper.

Every state-changing admin route writes one ``AdminAuditLog`` row
inside the same DB transaction as the mutation
(IMPLEMENTATION_PLAN section 8.4.4).  This module owns the
single function used everywhere so the diff structure stays
consistent and the row id can be returned in the response body.

The corresponding table is owned by Alembic migration ``0002_billing``
(originally introduced for billing) and hardened to append-only by
``0013_admin`` via REVOKE + a row-level trigger.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import AdminAuditLog


_REDACT_KEYS = {
    "password",
    "password_hash",
    "totp_secret",
    "totp_recovery_codes",
    "byok_api_key",
    "stripe_secret_key",
    "stripe_webhook_secret",
}


def _redact(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop / redact obvious secret fields before persisting.

    Does not attempt to walk arbitrary depth — callers are expected to
    pass shallow JSON dicts that summarise the affected fields, not
    full ORM rows.  The redactor is a defensive fallback only.
    """
    if not payload:
        return {}
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k.lower() in _REDACT_KEYS:
            out[k] = "***"
        else:
            out[k] = v
    return out


async def write_admin_audit(
    session: AsyncSession,
    *,
    actor_admin_id: uuid.UUID | None,
    action: str,
    target_kind: str,
    target_id: str,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    ip: str = "",
    user_agent: str = "",
    request_id: str = "",
) -> AdminAuditLog:
    """Persist an audit row and ``flush`` so its id is available.

    The row is created in the caller's transaction and committed when
    the caller commits.  No try/except here: we *want* the parent
    mutation to roll back if the audit row cannot be written.

    ``actor_admin_id`` may be ``None`` for system actions (e.g. the
    bootstrap super-admin creation); in that case the ``actor_admin_id``
    column stays NULL and the action name is the only attribution.
    """
    row = AdminAuditLog(
        id=uuid.uuid4(),
        actor_admin_id=actor_admin_id,
        action=action[:120],
        target_kind=target_kind[:80],
        target_id=str(target_id)[:255],
        before_json=_redact(before),
        after_json=_redact(after),
        ip=(ip or "")[:64],
        user_agent=(user_agent or "")[:512],
        request_id=(request_id or "")[:128],
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.flush()
    return row


__all__ = ["write_admin_audit"]
