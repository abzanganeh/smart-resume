"""Helpers shared across admin tests.

Provides factories that bypass the public 2FA flow so other tests can
focus on RBAC / audit / bootstrap behaviour without re-walking the
challenge token chain in every case.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminRole, AdminUser
from app.services.admin_auth.tokens import (
    create_admin_session_token,
    make_ua_fingerprint,
)
from app.services.auth.password import hash_password
from app.services.auth.totp import (
    begin_enrollment,
    generate_recovery_codes,
    hash_recovery_codes,
)


DEFAULT_PASSWORD = "tr0ub4dor&3sandwich-eats-paint"


async def make_admin(
    session: AsyncSession,
    *,
    email: str,
    role: AdminRole,
    password: str = DEFAULT_PASSWORD,
    enrolled_2fa: bool = True,
    suspended: bool = False,
    must_change_password: bool = False,
    must_enroll_2fa: bool = False,
) -> tuple[AdminUser, str]:
    """Insert an AdminUser row.  Returns (admin, totp_secret_b32)."""
    enrollment = begin_enrollment(account_label=f"admin:{email}")
    secret = enrollment.secret_b32 if enrolled_2fa else ""
    recovery_hashes: list[str] = []
    if enrolled_2fa:
        recovery_hashes = hash_recovery_codes(generate_recovery_codes(10))
    admin = AdminUser(
        id=uuid.uuid4(),
        email=email.strip().lower(),
        display_name=email.split("@", 1)[0],
        role=role,
        password_hash=hash_password(password),
        totp_secret=enrollment.encrypted_secret if enrolled_2fa else None,
        totp_recovery_codes=recovery_hashes,
        must_change_password=must_change_password,
        must_enroll_2fa=must_enroll_2fa,
        suspended_at=datetime.now(timezone.utc) if suspended else None,
        created_via="test",
    )
    session.add(admin)
    await session.flush()
    return admin, secret


async def issue_admin_session(
    admin_id: uuid.UUID,
    *,
    ip: str = "127.0.0.1",
    user_agent: str = "pytest",
    accept_language: str = "en-US",
) -> tuple[str, dict[str, str]]:
    """Mint a session token and return ``(token, headers)`` ready for httpx.

    Uses the same UA/IP plumbing the real router uses so the IP+UA
    binding check lines up.
    """
    ua_fp = make_ua_fingerprint(user_agent, accept_language)
    issued = await create_admin_session_token(admin_id, ip, ua_fp)
    headers = {
        "Authorization": f"Bearer {issued.token}",
        "User-Agent": user_agent,
        "Accept-Language": accept_language,
        "X-Forwarded-For": ip,
    }
    return issued.token, headers
