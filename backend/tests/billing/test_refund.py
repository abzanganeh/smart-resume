"""Refund workflow tests — admin approve/deny + 24h self-service (§18.3, Step 37)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.admin import AdminRole, AdminUser
from app.models.billing import (
    AdminAuditLog,
    RefundInitiator,
    RefundReason,
    RefundRecord,
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.notifications import Notification
from app.models.user import (
    AuthProvider,
    CreditTransaction,
    CreditTransactionAction,
    User,
    UserTier,
)
from app.services.billing import refund as refund_service
from app.services.billing.exceptions import RefundError

pytestmark = pytest.mark.integration


def _stripe_refund_response(refund_id: str | None = None) -> Any:
    class _Refund:
        def __init__(self, _id: str) -> None:
            self._id = _id

        def to_dict_recursive(self) -> dict[str, Any]:
            return {"id": self._id, "status": "succeeded"}

    return _Refund(refund_id or f"re_{uuid.uuid4().hex[:12]}")


async def _seed_user(session: AsyncSession, *, email: str | None = None) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email or f"refund-{uuid.uuid4().hex[:8]}@example.com",
        display_name="R",
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    session.add(user)
    await session.flush()
    return user


async def _seed_admin(session: AsyncSession) -> AdminUser:
    admin = AdminUser(
        id=uuid.uuid4(),
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Admin",
        role=AdminRole.super_admin,
        password_hash="x",
    )
    session.add(admin)
    await session.flush()
    return admin


async def _seed_recent_subscription(
    session: AsyncSession,
    *,
    user: User,
    created_at: datetime | None = None,
) -> Subscription:
    sub = Subscription(
        id=uuid.uuid4(),
        user_id=user.id,
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        status=SubscriptionStatus.active,
        period_start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 6, 1, tzinfo=timezone.utc),
        cancel_at_period_end=False,
        stripe_customer_id="cus_test",
        stripe_subscription_id=f"sub_{uuid.uuid4().hex[:12]}",
        stripe_price_id="price_monthly_test",
    )
    session.add(sub)
    await session.flush()
    if created_at is not None:
        # Override created_at directly (server_default normally sets it
        # to now()).
        sub.created_at = created_at
        await session.flush()
    return sub


async def test_self_service_24h_refund_calls_stripe_and_writes_audit(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 24h path calls Stripe directly and writes the audit row."""
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    user = await _seed_user(db_session)
    sub = await _seed_recent_subscription(
        db_session,
        user=user,
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    await db_session.commit()

    with patch(
        "app.services.billing.refund.stripe.Refund.create",
        return_value=_stripe_refund_response("re_self_service"),
    ) as create_mock:
        decision = await refund_service.self_service_refund(
            db_session,
            user=user,
            amount_usd=19.99,
            payment_intent="pi_test",
        )
    await db_session.commit()

    assert decision.stripe_refund_id == "re_self_service"
    create_mock.assert_called_once()

    # Refund record persisted with self_service_24h reason.
    row = (
        await db_session.execute(
            select(RefundRecord).where(RefundRecord.id == decision.record_id)
        )
    ).scalar_one()
    assert row.reason == RefundReason.self_service_24h
    assert row.initiated_by == RefundInitiator.user
    assert row.stripe_refund_id == "re_self_service"
    assert float(row.amount_usd) == pytest.approx(19.99)

    # AdminAuditLog row for the action.
    audits = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.target_id == str(decision.record_id)
                )
            )
        )
        .scalars()
        .all()
    )
    assert any(a.action == "refund_self_service" for a in audits)


async def test_self_service_24h_refund_window_expired_raises(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    user = await _seed_user(db_session)
    await _seed_recent_subscription(
        db_session,
        user=user,
        created_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    await db_session.commit()

    with patch(
        "app.services.billing.refund.stripe.Refund.create",
        return_value=_stripe_refund_response(),
    ):
        with pytest.raises(RefundError) as excinfo:
            await refund_service.self_service_refund(
                db_session,
                user=user,
                amount_usd=19.99,
                payment_intent="pi_test",
            )
    assert excinfo.value.stage == "window"


async def test_admin_refund_approve_calls_stripe_and_inserts_credit_reversal(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admin approve flow: Stripe refund + credit reversal + audit row."""
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    user = await _seed_user(db_session)
    sub = await _seed_recent_subscription(db_session, user=user)
    pending = RefundRecord(
        id=uuid.uuid4(),
        user_id=user.id,
        subscription_id=sub.id,
        stripe_refund_id=f"pending_{uuid.uuid4().hex}",
        amount_usd=29.99,
        reason=RefundReason.manual,
        initiated_by=RefundInitiator.user,
    )
    db_session.add(pending)
    admin = await _seed_admin(db_session)
    await db_session.commit()

    admin_id = admin.id
    with patch(
        "app.services.billing.refund.stripe.Refund.create",
        return_value=_stripe_refund_response("re_admin_approved"),
    ) as create_mock:
        decision = await refund_service.approve_refund(
            db_session,
            record_id=pending.id,
            admin_id=admin_id,
            amount_usd=29.99,
            reason_note="Customer reported double-charge",
            payment_intent="pi_test",
            credit_reverse_delta=2,
        )
    await db_session.commit()

    create_mock.assert_called_once()
    assert decision.stripe_refund_id == "re_admin_approved"

    row = (
        await db_session.execute(
            select(RefundRecord).where(RefundRecord.id == pending.id)
        )
    ).scalar_one()
    assert row.stripe_refund_id == "re_admin_approved"
    assert row.initiated_by == RefundInitiator.admin
    assert row.admin_id == admin_id

    # Credit reversal landed.
    reversal = (
        await db_session.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user.id)
            .where(
                CreditTransaction.action
                == CreditTransactionAction.refund_reverse
            )
        )
    ).scalar_one_or_none()
    assert reversal is not None
    assert reversal.delta == 2

    audits = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.target_id == str(pending.id)
                )
            )
        )
        .scalars()
        .all()
    )
    assert any(a.action == "refund_approved" for a in audits)


async def test_admin_refund_deny_writes_audit_and_notification(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session)
    sub = await _seed_recent_subscription(db_session, user=user)
    pending = RefundRecord(
        id=uuid.uuid4(),
        user_id=user.id,
        subscription_id=sub.id,
        stripe_refund_id=f"pending_{uuid.uuid4().hex}",
        amount_usd=49.99,
        reason=RefundReason.manual,
        initiated_by=RefundInitiator.user,
    )
    db_session.add(pending)
    admin = await _seed_admin(db_session)
    await db_session.commit()

    admin_id = admin.id
    decision = await refund_service.deny_refund(
        db_session,
        record_id=pending.id,
        admin_id=admin_id,
        reason_note="Outside the §18.3 refund window",
    )
    await db_session.commit()

    row = (
        await db_session.execute(
            select(RefundRecord).where(RefundRecord.id == pending.id)
        )
    ).scalar_one()
    assert row.admin_id == admin_id
    assert row.stripe_refund_id.startswith("denied_")
    audits = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.target_id == str(pending.id)
                )
            )
        )
        .scalars()
        .all()
    )
    assert any(a.action == "refund_denied" for a in audits)

    notifs = list(
        (
            await db_session.execute(
                select(Notification)
                .where(Notification.user_id == user.id)
                .where(Notification.type == "refund_denied")
            )
        )
        .scalars()
        .all()
    )
    assert len(notifs) == 2  # in_app + email
    assert any(
        "Outside" in (n.body or "") for n in notifs
    ), "denial reason must surface to the user"
