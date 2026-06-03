"""Bootstrap super-admin (IMPLEMENTATION_PLAN section 8.4.3).

A single startup hook that runs under a Postgres advisory lock so
parallel boots cannot race to create two super-admins.

Behaviour:

1. Acquire ``pg_advisory_lock(hashtext('bootstrap_super_admin'))``.
2. If any AdminUser with role=super_admin exists, return early and
   log ``bootstrap_skipped_existing_admin`` (the env vars are NOT
   used to update an existing record).
3. Otherwise create one row with:
   - ``email`` from ``BOOTSTRAP_SUPER_ADMIN_EMAIL``
   - ``role = super_admin``
   - ``must_change_password=True``, ``must_enroll_2fa=True``
   - ``created_via='bootstrap'``
   - bcrypt password hash from ``BOOTSTRAP_SUPER_ADMIN_PASSWORD``
4. Write one ``AdminAuditLog`` row with
   ``action='bootstrap_super_admin_created'`` and
   ``actor_admin_id=NULL`` (system action).
5. Release the advisory lock.

Password rules:

- ``staging`` / ``production``: ``BOOTSTRAP_SUPER_ADMIN_PASSWORD`` is
  required; absence aborts bootstrap with an audit row
  ``action='bootstrap_super_admin_aborted'``.
- ``local`` / ``development`` / ``ci``: a strong random password is
  generated and printed once to stdout.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import is_production_grade, settings
from app.models.admin import AdminRole, AdminUser
from app.models.user import AuthProvider, User, UserTier
from app.services.admin_auth.audit import write_admin_audit
from app.services.auth.password import hash_password

log = structlog.get_logger("admin.bootstrap")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Stable hash key for ``pg_advisory_lock``.  The Python ``hash()``
# would not be stable across processes, so we use a fixed integer
# derived once via ``hashtext`` semantics.
_BOOTSTRAP_LOCK_KEY = "bootstrap_super_admin"


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """Return value of :func:`bootstrap_super_admin`."""

    created: bool
    skipped_reason: Optional[str]
    admin_id: Optional[uuid.UUID]
    generated_password: Optional[str]


def _gen_password() -> str:
    """Generate a 32-character URL-safe password for local dev."""
    return secrets.token_urlsafe(24)


async def _ensure_linked_app_user(
    session: AsyncSession,
    email: str,
    password_hash: Optional[str] = None,
    display_name: str = "",
) -> None:
    """Idempotently ensure a regular User row exists for the bootstrap email.

    The linked user gets:
    - ``pro`` tier (no plan limits)
    - 999 999 free credits (effectively unlimited for testing)
    - pre-verified email (no email verification step)
    - same password hash as the admin account (if provided)

    Safe to call on every startup — it never degrades an existing account.
    """
    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if existing is None:
        user = User(
            id=uuid.uuid4(),
            email=email,
            display_name=display_name or email,
            auth_provider=AuthProvider.email,
            provider_id=None,
            password_hash=password_hash,
            tier=UserTier.pro,
            credit_balance=999_999,
            email_verified_at=_utcnow(),
            accepted_tos_version="bootstrap",
        )
        session.add(user)
        log.info(
            "admin.bootstrap.app_user_created",
            email=email,
            tier="pro",
            credits=999_999,
        )
    else:
        # Upgrade existing user but never downgrade.
        changed = False
        if existing.tier != UserTier.pro:
            existing.tier = UserTier.pro
            changed = True
        if existing.credit_balance < 999_999:
            existing.credit_balance = 999_999
            changed = True
        if existing.email_verified_at is None:
            existing.email_verified_at = _utcnow()
            changed = True
        if changed:
            log.info("admin.bootstrap.app_user_upgraded", email=email)
        else:
            log.info("admin.bootstrap.app_user_ok", email=email)


async def bootstrap_super_admin(session: AsyncSession) -> BootstrapResult:
    """Idempotently ensure exactly one super-admin row exists.

    Caller is responsible for committing.  When this function returns
    ``BootstrapResult(created=True, ...)`` the caller MUST commit so
    the row is persisted.
    """
    if not settings.BOOTSTRAP_SUPER_ADMIN_EMAIL:
        log.info("admin.bootstrap.skipped", reason="no_email_configured")
        return BootstrapResult(False, "no_email_configured", None, None)

    # Acquire the advisory lock for the duration of this transaction.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": _BOOTSTRAP_LOCK_KEY},
    )

    email = settings.BOOTSTRAP_SUPER_ADMIN_EMAIL.strip().lower()

    # Re-check existence under the lock.
    existing_count = (
        await session.execute(
            select(func.count())
            .select_from(AdminUser)
            .where(AdminUser.role == AdminRole.super_admin)
        )
    ).scalar() or 0
    if existing_count > 0:
        log.info(
            "admin.bootstrap.skipped",
            reason="bootstrap_skipped_existing_admin",
            count=int(existing_count),
        )
        # Even when skipping admin creation, ensure a linked app User exists
        # so the owner can log in to the app with the same credentials.
        await _ensure_linked_app_user(session, email)
        return BootstrapResult(
            False, "bootstrap_skipped_existing_admin", None, None
        )

    password = settings.BOOTSTRAP_SUPER_ADMIN_PASSWORD.strip()
    generated = False
    if not password:
        if is_production_grade() and settings.APP_ENV in {"staging", "production"}:
            await write_admin_audit(
                session,
                actor_admin_id=None,
                action="bootstrap_super_admin_aborted",
                target_kind="admin_user",
                target_id=settings.BOOTSTRAP_SUPER_ADMIN_EMAIL,
                after={"reason": "missing_password_env"},
            )
            log.error(
                "admin.bootstrap.aborted",
                reason="BOOTSTRAP_SUPER_ADMIN_PASSWORD required in staging/production",
            )
            return BootstrapResult(False, "missing_password_env", None, None)
        password = _gen_password()
        generated = True
        log.warning(
            "admin.bootstrap.generated_password",
            email=settings.BOOTSTRAP_SUPER_ADMIN_EMAIL,
            password=password,
        )
        # Print once to stdout per IMPLEMENTATION_PLAN section 8.4.3 so
        # the developer can copy it from the console even when log
        # capture is on.
        print(  # noqa: T201
            f"\n[bootstrap_super_admin] generated password for "
            f"{settings.BOOTSTRAP_SUPER_ADMIN_EMAIL}: {password}\n"
        )

    display_name = settings.BOOTSTRAP_SUPER_ADMIN_DISPLAY_NAME or email
    password_hash = hash_password(password)

    admin = AdminUser(
        id=uuid.uuid4(),
        email=email,
        display_name=display_name,
        role=AdminRole.super_admin,
        password_hash=password_hash,
        totp_secret=None,
        totp_recovery_codes=[],
        must_change_password=True,
        must_enroll_2fa=True,
        suspended_at=None,
        created_via="bootstrap",
        created_by_admin_id=None,
    )
    session.add(admin)
    await session.flush()

    await write_admin_audit(
        session,
        actor_admin_id=None,
        action="bootstrap_super_admin_created",
        target_kind="admin_user",
        target_id=str(admin.id),
        after={
            "email": admin.email,
            "role": admin.role.value,
            "created_via": "bootstrap",
            "must_change_password": True,
            "must_enroll_2fa": True,
        },
    )

    # Also create (or ensure) a linked regular User so the owner can log in
    # to the app itself and test it without limits.
    await _ensure_linked_app_user(session, email, password_hash=password_hash, display_name=display_name)

    log.info(
        "admin.bootstrap.created",
        admin_id=str(admin.id),
        email=admin.email,
        password_was_generated=generated,
    )
    return BootstrapResult(
        True,
        None,
        admin.id,
        password if generated else None,
    )


__all__ = ["BootstrapResult", "bootstrap_super_admin"]
