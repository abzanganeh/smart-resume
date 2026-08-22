"""Exhaustion top-up eligibility and grant tests."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.user import CreditTransactionAction, User, UserTier
from app.services.billing.exhaustion_top_up import (
    get_exhaustion_top_up_eligibility,
    grant_exhaustion_top_up,
)

pytestmark = pytest.mark.unit


def _user(**overrides: object) -> User:
    from app.models.user import AuthProvider

    base = {
        "id": uuid.uuid4(),
        "email": "user@example.com",
        "email_canonical": "user@example.com",
        "display_name": "User",
        "auth_provider": AuthProvider.email,
        "accepted_tos_version": "2026-06",
        "tier": UserTier.free,
        "email_verified_at": None,
        "signup_device_fingerprint_hash": "abc123",
    }
    base.update(overrides)
    return User(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_not_eligible_when_credits_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    from datetime import datetime, timezone

    user = _user(email_verified_at=datetime.now(timezone.utc))
    monkeypatch.setattr(
        "app.services.billing.exhaustion_top_up._has_active_subscription",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "app.services.billing.exhaustion_top_up.get_balance",
        AsyncMock(return_value=2),
    )
    result = await get_exhaustion_top_up_eligibility(session, user=user)
    assert result.eligible is False
    assert result.reason == "credits_remaining"


@pytest.mark.asyncio
async def test_eligible_when_verified_and_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime, timezone

    session = AsyncMock()
    user = _user(email_verified_at=datetime.now(timezone.utc))
    monkeypatch.setattr(
        "app.services.billing.exhaustion_top_up._has_active_subscription",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "app.services.billing.exhaustion_top_up.get_balance",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        "app.services.billing.exhaustion_top_up._top_up_already_used",
        AsyncMock(return_value=False),
    )
    result = await get_exhaustion_top_up_eligibility(session, user=user)
    assert result.eligible is True
    assert result.amount == 3
