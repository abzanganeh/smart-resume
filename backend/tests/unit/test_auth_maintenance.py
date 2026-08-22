"""Unverified account cleanup scheduler tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AuthProvider, User, UserTier
from app.services.auth.maintenance import soft_delete_unverified_accounts

pytestmark = pytest.mark.unit


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dry_run_does_not_suspend(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.auth.maintenance.settings.UNVERIFIED_ACCOUNT_CLEANUP_DAYS",
        7,
    )
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid.uuid4(),
        email="stale@example.com",
        email_canonical="stale@example.com",
        display_name="Stale",
        auth_provider=AuthProvider.email,
        password_hash="hash",
        tier=UserTier.free,
        accepted_tos_version="2026-06",
        created_at=now - timedelta(days=10),
    )
    db_session.add(user)
    await db_session.flush()

    result = await soft_delete_unverified_accounts(
        db_session,
        now=now,
        dry_run=True,
    )
    assert result.dry_run is True
    assert result.inspected == 1
    assert str(user.id) in result.suspended
    await db_session.refresh(user)
    assert user.suspended_at is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_run_suspends_stale_unverified_email_account(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid.uuid4(),
        email="old-unverified@example.com",
        email_canonical="old-unverified@example.com",
        display_name="Old",
        auth_provider=AuthProvider.email,
        password_hash="hash",
        tier=UserTier.free,
        accepted_tos_version="2026-06",
        created_at=now - timedelta(days=10),
    )
    db_session.add(user)
    await db_session.flush()

    result = await soft_delete_unverified_accounts(
        db_session,
        now=now,
        dry_run=False,
    )
    assert result.dry_run is False
    assert result.inspected == 1
    await db_session.refresh(user)
    assert user.suspended_at is not None
    assert user.suspension_reason == "email_not_verified_7d"
