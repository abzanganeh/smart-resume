"""Unit tests for free-credit spend eligibility helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.user import AuthProvider, User, UserTier
from app.services.billing.credit_spend import (
    credits_locked_detail,
    credits_locked_until_verification,
    spendable_free_credits,
)
from app.services.billing.exceptions import CreditsLockedUntilVerificationError
from app.services.billing.credits import consume_credit
from app.models.billing import CreditKind

pytestmark = pytest.mark.unit


def _user(*, verified: bool) -> User:
    return User(
        id=uuid.uuid4(),
        email="user@example.com",
        display_name="User",
        auth_provider=AuthProvider.email,
        password_hash="hash",
        tier=UserTier.free,
        credit_balance=3,
        email_verified_at=datetime.now(timezone.utc) if verified else None,
    )


def test_spendable_zero_when_unverified() -> None:
    user = _user(verified=False)
    assert spendable_free_credits(user, balance=6) == 0
    assert credits_locked_until_verification(user, balance=6) is True


def test_spendable_matches_balance_when_verified() -> None:
    user = _user(verified=True)
    assert spendable_free_credits(user, balance=6) == 6
    assert credits_locked_until_verification(user, balance=6) is False


def test_not_locked_when_balance_zero() -> None:
    user = _user(verified=False)
    assert credits_locked_until_verification(user, balance=0) is False


def test_credits_locked_detail_shape() -> None:
    detail = credits_locked_detail(balance=6)
    assert detail["code"] == "credits_locked_until_verification"
    assert detail["balance"] == 6


@pytest.mark.integration
@pytest.mark.asyncio
async def test_consume_credit_raises_when_unverified(db_session) -> None:
    user = _user(verified=False)
    db_session.add(user)
    await db_session.flush()

    from app.services.billing.credits import grant_credit

    await grant_credit(
        db_session,
        user_id=user.id,
        credit_kind=CreditKind.free,
        delta=6,
        reason="registration_grant",
    )

    with pytest.raises(CreditsLockedUntilVerificationError) as exc:
        await consume_credit(
            db_session,
            user_id=user.id,
            credit_kind=CreditKind.free,
            reason="resume_build",
        )
    assert exc.value.balance == 6
