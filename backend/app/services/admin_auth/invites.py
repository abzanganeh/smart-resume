"""Admin invite issuance / acceptance.

Super-admin -> ``POST /api/admin/auth/invite`` mints an opaque token
whose SHA-256 hash is persisted in ``admin_invites`` along with the
target ``email`` and ``role``.  The plaintext token is delivered via
the invite email.

Invitee -> ``POST /api/admin/auth/accept-invite`` presents the token,
chooses a password, and is forced through TOTP enrollment before any
real admin endpoint is reachable.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.admin import AdminInvite, AdminRole

log = structlog.get_logger("admin.invites")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CreatedInvite:
    """Return value of :func:`create_invite`.

    The plaintext ``token`` is only available immediately after
    creation and is delivered via email; subsequent reads via
    ``find_active_invite_by_token`` only succeed if the caller still
    holds the plaintext.
    """

    invite_id: uuid.UUID
    token: str
    expires_at: datetime


async def create_invite(
    session: AsyncSession,
    *,
    email: str,
    role: AdminRole,
    invited_by_admin_id: uuid.UUID,
    ttl_seconds: int | None = None,
) -> CreatedInvite:
    """Mint an invite token and persist its hash."""
    ttl = (
        ttl_seconds
        if ttl_seconds is not None
        else settings.ADMIN_INVITE_TTL_SECONDS
    )
    plaintext = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl)
    row = AdminInvite(
        id=uuid.uuid4(),
        email=email.strip().lower(),
        role=role,
        token_hash=_hash_token(plaintext),
        invited_by_admin_id=invited_by_admin_id,
        created_at=now,
        expires_at=expires_at,
        accepted_at=None,
        revoked_at=None,
        accepted_admin_id=None,
    )
    session.add(row)
    await session.flush()
    log.info(
        "admin.invite.created",
        invite_id=str(row.id),
        email=row.email,
        role=row.role.value,
    )
    return CreatedInvite(invite_id=row.id, token=plaintext, expires_at=expires_at)


async def find_active_invite_by_token(
    session: AsyncSession, token: str
) -> Optional[AdminInvite]:
    if not token:
        return None
    row = (
        await session.execute(
            select(AdminInvite).where(AdminInvite.token_hash == _hash_token(token))
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if not row.is_active:
        return None
    return row


async def revoke_invite(
    session: AsyncSession, invite_id: uuid.UUID
) -> bool:
    """Mark an invite revoked (idempotent).  Returns ``True`` if a row was
    transitioned, ``False`` if it was already inactive."""
    row = (
        await session.execute(
            select(AdminInvite).where(AdminInvite.id == invite_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    if row.revoked_at is not None or row.accepted_at is not None:
        return False
    row.revoked_at = datetime.now(timezone.utc)
    await session.flush()
    return True


__all__ = [
    "CreatedInvite",
    "create_invite",
    "find_active_invite_by_token",
    "revoke_invite",
]
