"""Concurrent credit consumption — ``SELECT … FOR UPDATE`` prevents double-spend.

Spawns N parallel ``consume_credit`` calls against a user with K free
credits where N > K and asserts:

- Exactly K succeed with ``delta=-1`` rows.
- The remaining N-K raise :class:`InsufficientCreditsError`.
- The final balance is zero.

Each consume runs in its own session/transaction (mirroring real
parallel HTTP requests).  Without the ``FOR UPDATE`` lock the projected
balance check would race and let multiple consumers drain past zero.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.billing import CreditKind
from app.models.user import (
    AuthProvider,
    CreditTransaction,
    CreditTransactionAction,
    User,
    UserTier,
)
from app.services.billing.credits import (
    consume_credit,
    get_balance,
    grant_credit,
)
from app.services.billing.exceptions import InsufficientCreditsError

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture()
async def parallel_engine():
    """Independent engine so each task can open its own AsyncSession."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    engine = create_async_engine(url, pool_size=10, max_overflow=10)
    yield engine
    await engine.dispose()


async def _seed_user(db_session: AsyncSession, *, free_credits: int) -> uuid.UUID:
    user = User(
        id=uuid.uuid4(),
        email="carol@example.com",
        display_name="Carol",
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    await db_session.flush()
    if free_credits > 0:
        await grant_credit(
            db_session,
            user_id=user.id,
            credit_kind=CreditKind.free,
            delta=free_credits,
            reason="registration_grant",
        )
    await db_session.commit()
    return user.id


async def test_concurrent_consumers_do_not_double_spend(
    db_session: AsyncSession, parallel_engine
) -> None:
    user_id = await _seed_user(db_session, free_credits=3)

    factory = async_sessionmaker(parallel_engine, expire_on_commit=False)

    async def _try_consume() -> bool:
        async with factory() as s:
            try:
                async with s.begin():
                    await consume_credit(
                        s,
                        user_id=user_id,
                        credit_kind=CreditKind.free,
                        reason="resume_build",
                    )
            except InsufficientCreditsError:
                return False
            return True

    # 8 parallel consumers vs. 3 credits → exactly 3 succeed.
    results = await asyncio.gather(*[_try_consume() for _ in range(8)])
    assert sum(1 for r in results if r) == 3
    assert sum(1 for r in results if not r) == 5

    # Final balance is zero.
    final = await get_balance(
        db_session, user_id=user_id, credit_kind=CreditKind.free
    )
    assert final == 0

    # The ledger has 4 rows: 1 grant + 3 consumes (no extras).
    rows = (
        await db_session.execute(
            CreditTransaction.__table__.select()
            .where(CreditTransaction.user_id == user_id)
        )
    ).all()
    deltas = sorted(r.delta for r in rows)
    assert deltas == [-1, -1, -1, 3]
    assert all(
        r.action == CreditTransactionAction.resume_build for r in rows if r.delta < 0
    )
