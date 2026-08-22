"""Card fingerprint storage and cross-account cluster flagging (M21 slice 7)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import PaymentCardFingerprint
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.card_fingerprint import (
    CARD_FINGERPRINT_CLUSTER_FLAG,
    extract_card_fingerprint,
    record_payment_card_fingerprint,
)

pytestmark = pytest.mark.unit


def test_extract_card_fingerprint_from_expanded_payment_intent() -> None:
    obj = {
        "payment_intent": {
            "payment_method": {
                "card": {"fingerprint": "fp_test_abc123"},
            }
        }
    }
    assert extract_card_fingerprint(obj) == "fp_test_abc123"


def test_extract_card_fingerprint_from_expanded_charge() -> None:
    obj = {
        "charge": {
            "payment_method_details": {
                "card": {"fingerprint": "fp_charge_xyz"},
            }
        }
    }
    assert extract_card_fingerprint(obj) == "fp_charge_xyz"


def test_extract_card_fingerprint_returns_none_when_missing() -> None:
    assert extract_card_fingerprint({"id": "cs_test"}) is None


async def _seed_user(db_session: AsyncSession, email_suffix: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"card-{email_suffix}@example.com",
        email_canonical=f"card-{email_suffix}@example.com",
        display_name="Card User",
        auth_provider=AuthProvider.email,
        password_hash="hash",
        tier=UserTier.free,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _checkout_obj(*, fingerprint: str) -> dict[str, Any]:
    return {
        "payment_intent": {
            "payment_method": {"card": {"fingerprint": fingerprint}},
        }
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_card_fingerprint_cluster_flags_three_accounts(
    db_session: AsyncSession,
) -> None:
    shared_fp = "shared-card-fingerprint"
    users = [await _seed_user(db_session, str(i)) for i in range(3)]

    for idx, user in enumerate(users):
        await record_payment_card_fingerprint(
            db_session,
            user_id=user.id,
            stripe_event_id=f"evt_card_{idx}",
            stripe_object=_checkout_obj(fingerprint=shared_fp),
        )

    for user in users:
        await db_session.refresh(user)
        assert user.signup_abuse_review_flag == CARD_FINGERPRINT_CLUSTER_FLAG

    rows = (
        await db_session.execute(select(PaymentCardFingerprint))
    ).scalars().all()
    assert len(rows) == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_card_fingerprint_does_not_flag_two_accounts(
    db_session: AsyncSession,
) -> None:
    shared_fp = "two-account-card"
    users = [await _seed_user(db_session, f"two-{i}") for i in range(2)]

    for idx, user in enumerate(users):
        await record_payment_card_fingerprint(
            db_session,
            user_id=user.id,
            stripe_event_id=f"evt_two_{idx}",
            stripe_object=_checkout_obj(fingerprint=shared_fp),
        )

    for user in users:
        await db_session.refresh(user)
        assert user.signup_abuse_review_flag is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_duplicate_stripe_event_is_idempotent(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, "idem")
    obj = _checkout_obj(fingerprint="idem-card")

    await record_payment_card_fingerprint(
        db_session,
        user_id=user.id,
        stripe_event_id="evt_idem_card",
        stripe_object=obj,
    )
    await record_payment_card_fingerprint(
        db_session,
        user_id=user.id,
        stripe_event_id="evt_idem_card",
        stripe_object=obj,
    )

    rows = (
        await db_session.execute(
            select(PaymentCardFingerprint).where(
                PaymentCardFingerprint.user_id == user.id
            )
        )
    ).scalars().all()
    assert len(rows) == 1
