"""Phase 3 LLM-upgrade routing — atomic credit / counter accounting.

Covers the §7.5 / §7.7 + §18.3 contract enforced by
:func:`apply_phase3_tier`:

1. ``better`` tier consumes exactly one ``CreditKind.better`` credit
   per run, even when N parallel runs race against the same balance.
2. ``best`` tier increments ``Subscription.upgraded_resumes_used`` and
   never exceeds the soft cap of 100.
3. Once the soft cap is reached, the same call falls back to
   ``standard`` and surfaces ``best_soft_cap_hit`` so the orchestrator
   can emit the matching SSE event.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.billing import (
    CreditKind,
    LLMUpgradeBillingCycle,
    LLMUpgradeTier,
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.user import (
    AuthProvider,
    CreditTransaction,
    User,
    UserTier,
)
from app.services.billing.credits import get_balance, grant_credit
from app.services.billing.exceptions import InsufficientCreditsError
from app.services.billing.llm_upgrade import (
    BEST_SUBSCRIPTION_SOFT_CAP,
    Phase3TierError,
    apply_phase3_tier,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture()
async def parallel_engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    engine = create_async_engine(url, pool_size=10, max_overflow=10)
    yield engine
    await engine.dispose()


async def _seed_user(db_session: AsyncSession, *, email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name=email.split("@", 1)[0],
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _seed_best_subscription(
    db_session: AsyncSession,
    *,
    user: User,
    upgraded_used: int = 0,
) -> Subscription:
    now = datetime.now(timezone.utc)
    sub = Subscription(
        id=uuid.uuid4(),
        user_id=user.id,
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        llm_upgrade=LLMUpgradeTier.best,
        llm_upgrade_billing_cycle=LLMUpgradeBillingCycle.monthly,
        status=SubscriptionStatus.active,
        period_start=now - timedelta(days=1),
        period_end=now + timedelta(days=29),
        upgraded_resumes_used=upgraded_used,
        cancel_at_period_end=False,
        stripe_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
        stripe_subscription_id=f"sub_best_{uuid.uuid4().hex[:8]}",
        stripe_price_id="price_best_monthly_test",
    )
    db_session.add(sub)
    await db_session.commit()
    return sub


# ---------------------------------------------------------------------------
# Better tier — atomic credit consumption
# ---------------------------------------------------------------------------


async def test_better_tier_consumes_one_credit_per_run(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, email="better-run@example.com")
    await grant_credit(
        db_session,
        user_id=user.id,
        credit_kind=CreditKind.better,
        delta=3,
        reason="purchase_better_5pack",
    )
    await db_session.commit()

    decision = await apply_phase3_tier(
        db_session,
        user_id=user.id,
        requested_tier="better",
    )
    await db_session.commit()
    assert decision.effective_tier == "better"
    assert decision.consumed_credit_id is not None
    assert decision.downgrade_reason is None

    balance = await get_balance(
        db_session, user_id=user.id, credit_kind=CreditKind.better
    )
    assert balance == 2


async def test_better_tier_concurrent_runs_do_not_double_consume(
    db_session: AsyncSession, parallel_engine
) -> None:
    user = await _seed_user(db_session, email="better-race@example.com")
    await grant_credit(
        db_session,
        user_id=user.id,
        credit_kind=CreditKind.better,
        delta=2,
        reason="purchase_better_5pack",
    )
    await db_session.commit()

    factory = async_sessionmaker(parallel_engine, expire_on_commit=False)

    async def _try_run() -> bool:
        async with factory() as s:
            try:
                async with s.begin():
                    await apply_phase3_tier(
                        s,
                        user_id=user.id,
                        requested_tier="better",
                    )
            except InsufficientCreditsError:
                return False
            return True

    # 5 parallel runs vs. 2 credits → exactly 2 succeed.
    results = await asyncio.gather(*[_try_run() for _ in range(5)])
    assert sum(1 for r in results if r) == 2
    assert sum(1 for r in results if not r) == 3

    final_balance = await get_balance(
        db_session, user_id=user.id, credit_kind=CreditKind.better
    )
    assert final_balance == 0

    # Ledger should show 1 grant + 2 consumes for ``better``.
    rows = (
        await db_session.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.credit_kind == CreditKind.better,
            )
        )
    ).scalars().all()
    deltas = sorted(r.delta for r in rows)
    assert deltas == [-1, -1, 2]


async def test_better_tier_without_credits_falls_back_to_standard(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, email="better-empty@example.com")

    decision = await apply_phase3_tier(
        db_session,
        user_id=user.id,
        requested_tier="better",
    )
    assert decision.effective_tier == "standard"
    assert decision.downgrade_reason is Phase3TierError.not_entitled_better


async def test_best_request_downgrades_to_better_when_entitled(
    db_session: AsyncSession,
) -> None:
    """Requested best should downgrade to better (not standard) when the
    user has Better entitlement but no Best subscription.
    """
    user = await _seed_user(db_session, email="best-to-better@example.com")
    await grant_credit(
        db_session,
        user_id=user.id,
        credit_kind=CreditKind.better,
        delta=1,
        reason="purchase_better_5pack",
    )
    await db_session.commit()

    decision = await apply_phase3_tier(
        db_session,
        user_id=user.id,
        requested_tier="best",
    )
    await db_session.commit()

    assert decision.effective_tier == "better"
    assert decision.downgrade_reason is None
    assert decision.consumed_credit_id is not None


# ---------------------------------------------------------------------------
# Best tier — atomic counter increment + soft cap
# ---------------------------------------------------------------------------


async def test_best_tier_increments_upgraded_resumes_used(
    db_session: AsyncSession,
) -> None:
    """User-prompt acceptance: tier=best run increments the counter."""
    user = await _seed_user(db_session, email="best-run@example.com")
    sub = await _seed_best_subscription(db_session, user=user, upgraded_used=42)

    decision = await apply_phase3_tier(
        db_session,
        user_id=user.id,
        requested_tier="best",
    )
    await db_session.commit()
    await db_session.refresh(sub)

    assert decision.effective_tier == "best"
    assert decision.incremented_subscription_id == sub.id
    assert sub.upgraded_resumes_used == 43


async def test_best_tier_at_soft_cap_falls_back_to_standard(
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, email="best-cap@example.com")
    sub = await _seed_best_subscription(
        db_session,
        user=user,
        upgraded_used=BEST_SUBSCRIPTION_SOFT_CAP,
    )

    decision = await apply_phase3_tier(
        db_session,
        user_id=user.id,
        requested_tier="best",
    )
    await db_session.commit()
    await db_session.refresh(sub)

    assert decision.effective_tier == "standard"
    assert decision.soft_cap_hit is True
    assert decision.downgrade_reason is Phase3TierError.best_soft_cap_hit
    # Counter must NOT be incremented past the cap.
    assert sub.upgraded_resumes_used == BEST_SUBSCRIPTION_SOFT_CAP


async def test_best_tier_concurrent_runs_respect_soft_cap(
    db_session: AsyncSession, parallel_engine
) -> None:
    """Concurrent best-tier runs serialize on the subscription row so
    ``upgraded_resumes_used`` never exceeds the soft cap.
    """
    user = await _seed_user(db_session, email="best-race@example.com")
    sub = await _seed_best_subscription(
        db_session,
        user=user,
        upgraded_used=BEST_SUBSCRIPTION_SOFT_CAP - 2,
    )

    factory = async_sessionmaker(parallel_engine, expire_on_commit=False)

    async def _try_run() -> str:
        async with factory() as s:
            async with s.begin():
                d = await apply_phase3_tier(
                    s, user_id=user.id, requested_tier="best"
                )
            return d.effective_tier

    # 5 parallel runs starting 2 below the cap → 2 succeed at "best",
    # the rest fall back to "standard" because the cap is reached.
    results = await asyncio.gather(*[_try_run() for _ in range(5)])
    assert sum(1 for r in results if r == "best") == 2
    assert sum(1 for r in results if r == "standard") == 3

    await db_session.refresh(sub)
    assert sub.upgraded_resumes_used == BEST_SUBSCRIPTION_SOFT_CAP
