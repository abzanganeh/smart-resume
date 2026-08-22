"""Flint / Career Flint metered credit scaffold (Strategy B §3.2).

Scaffold defaults from the integration plan — admin-configurable table
is deferred.  Holds live in-process until the ``pending_holds`` migration
lands; sufficient for Phase 3 API contract tests.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Final

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import CreditKind
from app.models.user import CreditTransaction, CreditTransactionAction, User
from app.services.billing.credits import get_balance
from app.services.billing.credit_spend import credits_locked_until_verification
from app.services.billing.exceptions import (
    CreditsLockedUntilVerificationError,
    InsufficientCreditsError,
)

log = structlog.get_logger("billing.flint_credits")

FLINT_PRODUCT: Final[str] = "career_flint"

# Strategy B §3.2 example costs (scaffold defaults — user-approved 2026-07-09).
FLINT_ACTION_COSTS: Final[dict[str, int]] = {
    "digest_extraction": 10,
    "pre_warm": 50,
    "rehearsal_turn": 15,
    "research_chat_msg": 8,
    "live_turn": 15,
    "mock_grade": 25,
}


@dataclass
class PendingHold:
    hold_id: uuid.UUID
    user_id: uuid.UUID
    session_id: str
    amount: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# In-process hold store — replaced by Postgres ``pending_holds`` in full Phase 3.
_HOLDS: dict[uuid.UUID, PendingHold] = {}


def flint_action_cost(action: str, *, product: str = FLINT_PRODUCT) -> int:
    if product != FLINT_PRODUCT:
        raise ValueError(f"unsupported product: {product!r}")
    try:
        return FLINT_ACTION_COSTS[action]
    except KeyError as exc:
        raise ValueError(f"unknown Flint action: {action!r}") from exc


async def deduct_flint_credits(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    action: str,
    product: str,
    session_id: str | None = None,
) -> tuple[int, uuid.UUID]:
    """Debit ``action`` cost from the user's ``free`` ledger (career_flint scaffold)."""
    cost = flint_action_cost(action, product=product)
    if cost <= 0:
        raise ValueError("cost must be positive")

    locked = await session.execute(
        select(User.id).where(User.id == user_id).with_for_update()
    )
    if locked.scalar_one_or_none() is None:
        raise InsufficientCreditsError(CreditKind.free.value, 0)

    user = await session.get(User, user_id)
    balance = await get_balance(session, user_id=user_id, credit_kind=CreditKind.free)
    if user is not None and credits_locked_until_verification(user, balance=balance):
        raise CreditsLockedUntilVerificationError(balance=balance)
    if balance < cost:
        raise InsufficientCreditsError(CreditKind.free.value, balance)

    row = CreditTransaction(
        id=uuid.uuid4(),
        user_id=user_id,
        delta=-cost,
        action=CreditTransactionAction.llm_upgrade_pack_use,
        reason=f"flint:{product}:{action}",
        credit_kind=CreditKind.free,
        session_id=session_id,
        note=f"product={product} action={action} cost={cost}",
    )
    session.add(row)
    await session.flush()

    new_balance = balance - cost
    user = await session.get(User, user_id)
    if user is not None:
        user.credit_balance = max(0, new_balance)
        await session.flush()

    log.info(
        "billing.flint_credits.deducted",
        user_id=str(user_id),
        action=action,
        product=product,
        cost=cost,
        balance=new_balance,
    )
    return new_balance, row.id


def create_hold(*, user_id: uuid.UUID, session_id: str, amount: int) -> uuid.UUID:
    if amount <= 0:
        raise ValueError("hold amount must be positive")
    hold_id = uuid.uuid4()
    _HOLDS[hold_id] = PendingHold(
        hold_id=hold_id,
        user_id=user_id,
        session_id=session_id,
        amount=amount,
    )
    log.info(
        "billing.flint_credits.hold_created",
        hold_id=str(hold_id),
        user_id=str(user_id),
        session_id=session_id,
        amount=amount,
    )
    return hold_id


def release_hold(*, hold_id: uuid.UUID, user_id: uuid.UUID) -> None:
    hold = _HOLDS.pop(hold_id, None)
    if hold is None:
        raise KeyError(f"hold not found: {hold_id}")
    if hold.user_id != user_id:
        _HOLDS[hold_id] = hold
        raise PermissionError("hold belongs to another user")
    log.info(
        "billing.flint_credits.hold_released",
        hold_id=str(hold_id),
        user_id=str(user_id),
    )


def reset_holds_for_tests() -> None:
    """Test-only — clear the in-process hold map."""
    _HOLDS.clear()


__all__ = [
    "FLINT_ACTION_COSTS",
    "FLINT_PRODUCT",
    "create_hold",
    "deduct_flint_credits",
    "flint_action_cost",
    "release_hold",
    "reset_holds_for_tests",
]
