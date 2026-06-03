"""Mandatory TOTP enrollment / verification for admin accounts.

Re-uses the user-side primitives (``begin_enrollment``,
``verify_totp_code``, ``generate_recovery_codes``,
``hash_recovery_codes``) so the cryptographic surface stays uniform,
but adds two admin-specific entry points:

- :func:`admin_enroll_totp` -- called once per admin from the
  ``admin_2fa_setup`` flow.  Atomically writes the encrypted secret
  to the AdminUser row and returns the provisioning URI for QR
  rendering.

- :func:`admin_verify_totp` -- accepts a 6-digit code (or one of the
  10 recovery codes) and, on a successful verify, mints the bcrypt
  recovery hashes and clears ``must_enroll_2fa``.

Per IMPLEMENTATION_PLAN section 8.4.2:

- 10 recovery codes shown ONCE at enrollment.
- 2FA cannot be self-disabled; only a super-admin may reset another
  admin's 2FA, and that reset is itself audited.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pyotp
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminUser
from app.services.auth.encryption import decrypt_bytes
from app.services.auth.totp import (
    ISSUER,
    RECOVERY_CODE_COUNT,
    begin_enrollment,
    consume_recovery_code,
    generate_recovery_codes,
    hash_recovery_codes,
    verify_totp_code,
)

log = structlog.get_logger("admin.totp")


@dataclass(frozen=True, slots=True)
class AdminEnrollmentResult:
    """Returned by ``admin_enroll_totp``.

    ``secret_b32`` is shown to the admin in the QR / fallback string.
    The plaintext recovery codes are *not* part of this dataclass --
    they are minted only on successful verify (see
    :func:`admin_verify_totp`).
    """

    secret_b32: str
    provisioning_uri: str


async def _load_admin_for_update(
    session: AsyncSession, admin_id: uuid.UUID
) -> AdminUser:
    row = (
        await session.execute(
            select(AdminUser).where(AdminUser.id == admin_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise LookupError(f"admin {admin_id!s} not found")
    return row


def _provisioning_uri_for_admin(admin: AdminUser, secret_b32: str) -> str:
    return pyotp.totp.TOTP(secret_b32).provisioning_uri(
        name=f"admin:{admin.email}",
        issuer_name=ISSUER,
    )


async def admin_enroll_totp(
    session: AsyncSession, admin_id: uuid.UUID
) -> AdminEnrollmentResult:
    """Generate a fresh TOTP secret + provisioning URI for ``admin_id``.

    When a secret was already written during a prior enroll attempt but
    confirmation has not completed yet, return that same secret so a
    page refresh or second login does not invalidate the user's
    authenticator entry.  A brand-new secret is minted only when none
    exists yet.
    """
    admin = await _load_admin_for_update(session, admin_id)
    if admin.totp_secret is not None:
        secret_b32 = decrypt_bytes(admin.totp_secret).decode("utf-8")
        log.info("admin.totp.enroll_reuse", admin_id=str(admin.id))
        return AdminEnrollmentResult(
            secret_b32=secret_b32,
            provisioning_uri=_provisioning_uri_for_admin(admin, secret_b32),
        )
    enrollment = begin_enrollment(account_label=f"admin:{admin.email}")
    admin.totp_secret = enrollment.encrypted_secret
    admin.totp_recovery_codes = []  # invalidate any prior partial enrollment
    await session.flush()
    log.info("admin.totp.enroll", admin_id=str(admin.id))
    return AdminEnrollmentResult(
        secret_b32=enrollment.secret_b32,
        provisioning_uri=enrollment.provisioning_uri,
    )


@dataclass(frozen=True, slots=True)
class AdminVerifyResult:
    """Returned by ``admin_verify_totp`` on first-time enrollment.

    ``recovery_codes`` is the plaintext list of 10 single-use codes;
    the caller MUST surface them to the admin exactly once (we never
    show them again).  On subsequent verifications (after enrollment
    is complete) ``recovery_codes`` is ``None``.
    """

    ok: bool
    enrolled_now: bool
    recovery_codes: list[str] | None


async def admin_verify_totp(
    session: AsyncSession,
    admin_id: uuid.UUID,
    code: str,
) -> AdminVerifyResult:
    """Verify a TOTP or recovery code for ``admin_id``.

    Returns ``AdminVerifyResult(ok=False, ...)`` for any failure path so
    callers can render a uniform 401 without leaking the reason.
    """
    admin = await _load_admin_for_update(session, admin_id)
    if admin.totp_secret is None:
        return AdminVerifyResult(ok=False, enrolled_now=False, recovery_codes=None)

    code = (code or "").strip()
    if not code:
        return AdminVerifyResult(ok=False, enrolled_now=False, recovery_codes=None)

    # Path A: 6-digit TOTP.
    if code.isdigit() and len(code) == 6:
        if verify_totp_code(admin.totp_secret, code):
            return await _finalize_verify(session, admin)
        return AdminVerifyResult(ok=False, enrolled_now=False, recovery_codes=None)

    # Path B: recovery code (only if recovery hashes have been minted).
    if admin.totp_recovery_codes:
        matched, remaining = consume_recovery_code(
            admin.totp_recovery_codes, code=code
        )
        if matched:
            admin.totp_recovery_codes = remaining
            await session.flush()
            return AdminVerifyResult(ok=True, enrolled_now=False, recovery_codes=None)
    return AdminVerifyResult(ok=False, enrolled_now=False, recovery_codes=None)


async def _finalize_verify(
    session: AsyncSession, admin: AdminUser
) -> AdminVerifyResult:
    """First-time successful verify: mint recovery codes, clear flags."""
    if not admin.totp_recovery_codes:
        plaintext = generate_recovery_codes(RECOVERY_CODE_COUNT)
        admin.totp_recovery_codes = hash_recovery_codes(plaintext)
        admin.must_enroll_2fa = False
        await session.flush()
        log.info("admin.totp.enrolled_complete", admin_id=str(admin.id))
        return AdminVerifyResult(
            ok=True, enrolled_now=True, recovery_codes=plaintext
        )
    return AdminVerifyResult(ok=True, enrolled_now=False, recovery_codes=None)


async def admin_reset_totp(
    session: AsyncSession,
    admin_id: uuid.UUID,
) -> None:
    """Wipe TOTP state so the admin must re-enroll on next login.

    Only callable by super-admin from the admin router; the audit row
    is written in the route handler.
    """
    admin = await _load_admin_for_update(session, admin_id)
    admin.totp_secret = None
    admin.totp_recovery_codes = []
    admin.must_enroll_2fa = True
    await session.flush()


__all__ = [
    "AdminEnrollmentResult",
    "AdminVerifyResult",
    "admin_enroll_totp",
    "admin_reset_totp",
    "admin_verify_totp",
]
