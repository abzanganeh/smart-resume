"""Tests for the bootstrap super-admin startup hook (IMPLEMENTATION_PLAN section 8.4.3).

The tests assert:

- A single super-admin is created on first boot.
- A second invocation is a no-op (idempotent under the advisory lock).
- The audit table records exactly one ``bootstrap_super_admin_created``
  entry across both invocations.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.admin import AdminRole, AdminUser
from app.models.billing import AdminAuditLog
from app.services.admin_auth.bootstrap import bootstrap_super_admin


@pytest.mark.asyncio
async def test_bootstrap_creates_super_admin_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "BOOTSTRAP_SUPER_ADMIN_EMAIL", "boot@example.com")
    monkeypatch.setattr(
        settings, "BOOTSTRAP_SUPER_ADMIN_PASSWORD", "S3cur3-Test-Password!"
    )
    monkeypatch.setattr(settings, "BOOTSTRAP_SUPER_ADMIN_DISPLAY_NAME", "Boot Admin")
    monkeypatch.setattr(settings, "APP_ENV", "development")

    # Hot path
    res1 = await bootstrap_super_admin(db_session)
    assert res1.created is True
    assert res1.admin_id is not None
    await db_session.commit()

    super_admin_count = (
        await db_session.execute(
            select(func.count())
            .select_from(AdminUser)
            .where(AdminUser.role == AdminRole.super_admin)
        )
    ).scalar()
    assert super_admin_count == 1

    admin = (
        await db_session.execute(
            select(AdminUser).where(AdminUser.role == AdminRole.super_admin)
        )
    ).scalar_one()
    assert admin.email == "boot@example.com"
    assert admin.must_change_password is True
    assert admin.must_enroll_2fa is True
    assert admin.created_via == "bootstrap"

    # Replay - must be a no-op
    res2 = await bootstrap_super_admin(db_session)
    assert res2.created is False
    assert res2.skipped_reason == "bootstrap_skipped_existing_admin"
    await db_session.commit()

    super_admin_count = (
        await db_session.execute(
            select(func.count())
            .select_from(AdminUser)
            .where(AdminUser.role == AdminRole.super_admin)
        )
    ).scalar()
    assert super_admin_count == 1

    audit_count = (
        await db_session.execute(
            select(func.count())
            .select_from(AdminAuditLog)
            .where(AdminAuditLog.action == "bootstrap_super_admin_created")
        )
    ).scalar()
    assert audit_count == 1, "Replay must not write a second bootstrap audit row"


@pytest.mark.asyncio
async def test_bootstrap_backfills_app_user_password_on_skip(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When super-admin already exists, linked User rows missing password_hash get backfilled."""
    from app.models.user import AuthProvider, User

    monkeypatch.setattr(settings, "BOOTSTRAP_SUPER_ADMIN_EMAIL", "boot@example.com")
    monkeypatch.setattr(
        settings, "BOOTSTRAP_SUPER_ADMIN_PASSWORD", "S3cur3-Test-Password!"
    )
    monkeypatch.setattr(settings, "APP_ENV", "staging")

    res1 = await bootstrap_super_admin(db_session)
    assert res1.created is True
    await db_session.commit()

    app_user = (
        await db_session.execute(
            select(User).where(User.email == "boot@example.com")
        )
    ).scalar_one()
    app_user.password_hash = None
    await db_session.commit()

    res2 = await bootstrap_super_admin(db_session)
    assert res2.created is False
    assert res2.skipped_reason == "bootstrap_skipped_existing_admin"
    await db_session.commit()

    app_user = (
        await db_session.execute(
            select(User).where(User.email == "boot@example.com")
        )
    ).scalar_one()
    assert app_user.password_hash is not None
    assert app_user.auth_provider == AuthProvider.email


@pytest.mark.asyncio
async def test_bootstrap_skipped_when_email_unset(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "BOOTSTRAP_SUPER_ADMIN_EMAIL", "")
    res = await bootstrap_super_admin(db_session)
    assert res.created is False
    assert res.skipped_reason == "no_email_configured"


@pytest.mark.asyncio
async def test_bootstrap_generates_password_in_dev(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(settings, "BOOTSTRAP_SUPER_ADMIN_EMAIL", "dev@example.com")
    monkeypatch.setattr(settings, "BOOTSTRAP_SUPER_ADMIN_PASSWORD", "")
    monkeypatch.setattr(settings, "APP_ENV", "development")

    res = await bootstrap_super_admin(db_session)
    assert res.created is True
    assert res.generated_password is not None
    assert len(res.generated_password) >= 24
    out = capsys.readouterr().out
    assert "bootstrap_super_admin" in out
    assert res.generated_password in out
