"""Credit ledger helpers — single source of truth per IMPLEMENTATION_PLAN §7.5.

Balance = ``SUM(credit_transactions.delta) WHERE user_id=? AND credit_kind=?``.

The legacy ``users.credit_balance`` column is now a *denormalized cache*
(updated alongside ledger writes for the ``free`` kind so the existing
``GET /api/auth/me`` response shape keeps working).  Reads should
prefer :func:`get_balance`.

Concurrency: :func:`consume_credit` uses a row-locking projection so
two parallel phase-3 runs cannot double-spend the same credit.  We
serialise on the user row (``users.id``) with ``SELECT … FOR UPDATE``
because the ledger itself is append-only.
"""

from __future__ import annotations

import uuid
from typing import Optional

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import CreditKind
from app.models.user import (
    CreditTransaction,
    CreditTransactionAction,
    User,
)
from app.services.billing.credit_spend import credits_locked_until_verification
from app.services.billing.exceptions import (
    CreditsLockedUntilVerificationError,
    InsufficientCreditsError,
)

log = structlog.get_logger("billing.credits")


# Map of free-form ``reason`` strings → categorical action enum.  The
# enum is kept for back-compat with §18.3 audit reads; new code should
# always pass ``reason``.
_REASON_TO_ACTION: dict[str, CreditTransactionAction] = {
    "registration_grant": CreditTransactionAction.registration_grant,
    "resume_build": CreditTransactionAction.resume_build,
    "ats_recalc": CreditTransactionAction.ats_recalc,
    "cover_letter": CreditTransactionAction.cover_letter,
    "section_regen": CreditTransactionAction.section_regen,
    "purchase_better_pack": CreditTransactionAction.llm_upgrade_pack,
    "purchase_better_5pack": CreditTransactionAction.llm_upgrade_pack,
    "purchase_best_per_resume": CreditTransactionAction.llm_upgrade_pack,
    "phase3_run_better": CreditTransactionAction.llm_upgrade_pack_use,
    "phase3_run_best": CreditTransactionAction.llm_upgrade_pack_use,
    "admin_grant": CreditTransactionAction.admin_grant,
    "admin_user_grant": CreditTransactionAction.admin_grant,
    "promo_redeem": CreditTransactionAction.admin_grant,
    "admin_revoke": CreditTransactionAction.admin_revoke,
    "pricing_restructure_expire_addon": CreditTransactionAction.admin_revoke,
    "refund": CreditTransactionAction.refund_reverse,
    "exhaustion_top_up": CreditTransactionAction.exhaustion_top_up,
    "purchase_credits_5": CreditTransactionAction.credit_pack_purchase,
    "purchase_credits_15": CreditTransactionAction.credit_pack_purchase,
    "backfill_legacy_balance": CreditTransactionAction.admin_grant,
}


def _action_for(reason: str, *, fallback: CreditTransactionAction) -> CreditTransactionAction:
    return _REASON_TO_ACTION.get(reason, fallback)


async def get_balance(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    credit_kind: CreditKind,
    for_share: bool = True,
) -> int:
    """Return ``SUM(delta)`` for ``(user_id, credit_kind)``.

    ``for_share=True`` issues ``SELECT … FOR SHARE`` on the projection
    so concurrent consumers see a consistent view inside a transaction
    (§7.5).  Default is the cheaper non-locking aggregate used for the
    ``GET /api/credits/balance`` endpoint.
    """
    stmt = (
        select(func.coalesce(func.sum(CreditTransaction.delta), 0))
        .where(CreditTransaction.user_id == user_id)
        .where(CreditTransaction.credit_kind == credit_kind)
    )
    if for_share:
        # PostgreSQL does not allow FOR SHARE directly on aggregate-only
        # SELECTs. Lock the source rows in a companion query, then compute SUM.
        await session.execute(
            select(CreditTransaction.id)
            .where(CreditTransaction.user_id == user_id)
            .where(CreditTransaction.credit_kind == credit_kind)
            .with_for_update(read=True)
        )
    return int((await session.execute(stmt)).scalar() or 0)


async def grant_credit(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    credit_kind: CreditKind,
    delta: int,
    reason: str,
    stripe_event_id: str | None = None,
    related_subscription_id: uuid.UUID | None = None,
    related_resume_record_id: uuid.UUID | None = None,
    admin_id: uuid.UUID | None = None,
    note: str | None = None,
) -> CreditTransaction:
    """Insert a positive-delta ledger row.

    The caller is responsible for committing.  The unique partial index
    ``(stripe_event_id, credit_kind)`` ensures duplicate webhook
    deliveries cannot grant credits twice (§7.4 idempotency).
    """
    if delta <= 0:
        raise ValueError("grant_credit requires a positive delta")
    row = CreditTransaction(
        id=uuid.uuid4(),
        user_id=user_id,
        delta=delta,
        action=_action_for(reason, fallback=CreditTransactionAction.admin_grant),
        reason=reason,
        credit_kind=credit_kind,
        admin_id=admin_id,
        note=note,
        stripe_event_id=stripe_event_id,
        related_subscription_id=related_subscription_id,
        related_resume_record_id=related_resume_record_id,
    )
    session.add(row)
    await session.flush()
    if credit_kind == CreditKind.free:
        await _refresh_user_credit_balance_cache(session, user_id=user_id)
    return row


async def consume_credit(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    credit_kind: CreditKind,
    reason: str,
    session_id: str | None = None,
    related_resume_record_id: uuid.UUID | None = None,
) -> CreditTransaction:
    """Consume one credit of ``credit_kind`` from ``user_id``.

    Acquires ``SELECT … FOR UPDATE`` on the user row so two parallel
    consumes cannot both succeed against the same balance.  Raises
    :class:`InsufficientCreditsError` (HTTP 402) when the projected
    balance is zero or negative.
    """
    # Lock the user row so concurrent consumes serialize.
    locked = await session.execute(
        select(User.id).where(User.id == user_id).with_for_update()
    )
    if locked.scalar_one_or_none() is None:
        raise InsufficientCreditsError(credit_kind.value, 0)

    user = await session.get(User, user_id)

    # Also lock existing ledger rows for this (user, kind) projection so
    # the "check then insert" path is strictly serialized at the balance source.
    await session.execute(
        select(CreditTransaction.id)
        .where(CreditTransaction.user_id == user_id)
        .where(CreditTransaction.credit_kind == credit_kind)
        .with_for_update()
    )
    balance = await get_balance(
        session, user_id=user_id, credit_kind=credit_kind, for_share=False
    )
    if (
        credit_kind == CreditKind.free
        and user is not None
        and credits_locked_until_verification(user, balance=balance)
    ):
        raise CreditsLockedUntilVerificationError(balance=balance)
    if balance <= 0:
        raise InsufficientCreditsError(credit_kind.value, balance)

    row = CreditTransaction(
        id=uuid.uuid4(),
        user_id=user_id,
        delta=-1,
        action=_action_for(
            reason, fallback=CreditTransactionAction.llm_upgrade_pack_use
        ),
        reason=reason,
        credit_kind=credit_kind,
        session_id=session_id,
        related_resume_record_id=related_resume_record_id,
    )
    session.add(row)
    await session.flush()
    if credit_kind == CreditKind.free:
        await _refresh_user_credit_balance_cache(session, user_id=user_id)
    return row


async def record_quota_audit(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    reason: str,
    session_id: str | None = None,
) -> CreditTransaction:
    """Record a zero-delta quota event (first free use tracking)."""
    row = CreditTransaction(
        id=uuid.uuid4(),
        user_id=user_id,
        delta=0,
        action=_action_for(reason, fallback=CreditTransactionAction.llm_upgrade_pack_use),
        reason=reason,
        credit_kind=CreditKind.free,
        session_id=session_id,
    )
    session.add(row)
    await session.flush()
    return row


async def _refresh_user_credit_balance_cache(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> None:
    """Keep ``users.credit_balance`` in sync with the ``free`` ledger SUM.

    The column survives as a denormalized cache for the existing
    ``GET /api/auth/me`` response shape; the ledger is the source of
    truth.
    """
    free_balance = await get_balance(
        session, user_id=user_id, credit_kind=CreditKind.free
    )
    user: Optional[User] = await session.get(User, user_id)
    if user is not None:
        user.credit_balance = max(0, free_balance)
        await session.flush()


__all__ = [
    "consume_credit",
    "get_balance",
    "grant_credit",
    "record_quota_audit",
]
