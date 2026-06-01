"""Refund workflow integration (§18.3, §7.6, Step 37).

Three entry points:

- :func:`approve_refund` — admin super-admin clicks Approve in the UI.
  Calls Stripe ``refunds.create``, updates the :class:`RefundRecord`
  with the real ``stripe_refund_id``, inserts a
  :class:`CreditTransaction` reversal for any credits granted as part
  of the original purchase, and writes one :class:`AdminAuditLog` row
  inside the same transaction.

- :func:`deny_refund` — admin denies the request.  Updates the
  :class:`RefundRecord` (no Stripe call), writes one
  :class:`AdminAuditLog` row, and queues an in-app + email
  notification carrying the denial reason.

- :func:`self_service_refund` — user clicks "Refund" within 24h of
  the first paid charge (§18.3 row 1).  Auto-approves: calls
  Stripe directly, persists the :class:`RefundRecord`, and writes
  an :class:`AdminAuditLog` row with ``actor_admin_id=None`` so the
  audit trail still captures the action.

All three paths are pure service functions — no FastAPI imports —
so :mod:`backend.app.routers.billing` and :mod:`backend.app.routers.admin`
can call them without circular dependencies.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import stripe
import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import (
    AdminAuditLog,
    CreditKind,
    RefundInitiator,
    RefundReason,
    RefundRecord,
    Subscription,
)
from app.models.notifications import NotificationChannel
from app.models.user import (
    CreditTransaction,
    CreditTransactionAction,
    User,
)
from app.services.billing.exceptions import RefundError
from app.services.notifications.factory import build_notification

log = structlog.get_logger("billing.refund")


# Self-service refund window (§18.3 row 1).  Configurable so tests can
# narrow it without rewriting the seed timestamps.
SELF_SERVICE_WINDOW_HOURS = 24


@dataclass(frozen=True, slots=True)
class RefundDecision:
    record_id: uuid.UUID
    audit_id: uuid.UUID
    stripe_refund_id: str | None = None


def _configure_stripe() -> None:
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY


def _to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return {"raw": str(obj)}


async def _run_in_thread(fn, *args, **kwargs):
    clean_kwargs = {k: v for k, v in kwargs.items() if v is not None}
    return await asyncio.to_thread(fn, *args, **clean_kwargs)


def _amount_cents(amount_usd: float) -> int:
    return int(round(float(amount_usd) * 100))


async def _latest_subscription(
    session: AsyncSession, *, user_id: uuid.UUID
) -> Subscription | None:
    return (
        await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(desc(Subscription.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()


async def _stripe_create_refund(
    *,
    payment_intent: str | None,
    charge: str | None,
    amount_cents: int | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Call ``stripe.Refund.create`` off the event loop and normalize.

    Pass either ``payment_intent`` or ``charge``.  Stripe accepts
    ``amount`` as integer cents — passing ``None`` refunds the full
    charge.  Tests monkeypatch ``stripe.Refund.create`` and never hit
    the network.
    """
    _configure_stripe()
    kwargs: dict[str, Any] = {"metadata": metadata}
    if payment_intent:
        kwargs["payment_intent"] = payment_intent
    elif charge:
        kwargs["charge"] = charge
    if amount_cents is not None and amount_cents > 0:
        kwargs["amount"] = amount_cents
    try:
        result = await _run_in_thread(stripe.Refund.create, **kwargs)
    except Exception as exc:  # noqa: BLE001 — translate any Stripe error
        log.error("billing.refund.stripe_failed", error=str(exc))
        raise RefundError(stage="stripe", message=str(exc)) from exc
    return _to_dict(result)


async def _emit_credit_reverse(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    delta: int,
    refund_record_id: uuid.UUID,
    note: str,
) -> CreditTransaction | None:
    """Insert a ``refund_reverse`` ledger row when ``delta > 0``.

    No-op when there are no credits to reverse — pure subscription
    refunds (no credit grants attached) skip this without raising.
    """
    if delta <= 0:
        return None
    row = CreditTransaction(
        id=uuid.uuid4(),
        user_id=user_id,
        delta=delta,
        action=CreditTransactionAction.refund_reverse,
        reason=f"refund:{refund_record_id}",
        credit_kind=CreditKind.free,
        note=note,
    )
    session.add(row)
    await session.flush()
    return row


async def _emit_audit(
    session: AsyncSession,
    *,
    actor_admin_id: uuid.UUID | None,
    action: str,
    target_id: str,
    before: dict[str, Any],
    after: dict[str, Any],
    ip: str = "system:refund",
    user_agent: str = "billing.refund",
) -> uuid.UUID:
    audit_id = uuid.uuid4()
    session.add(
        AdminAuditLog(
            id=audit_id,
            actor_admin_id=actor_admin_id,
            action=action,
            target_kind="refund_record",
            target_id=target_id,
            before_json=before,
            after_json=after,
            ip=ip,
            user_agent=user_agent,
            request_id="",
        )
    )
    await session.flush()
    return audit_id


async def _send_user_notification(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    notification_type: str,
    title: str,
    body: str,
    data: dict[str, Any],
) -> None:
    for channel in (NotificationChannel.in_app, NotificationChannel.email):
        session.add(
            build_notification(
                user_id=user_id,
                type=notification_type,
                channel=channel,
                category="payment",
                title=title,
                body=body,
                data=data,
            )
        )
    await session.flush()


# ---------------------------------------------------------------------------
# Public service entry points
# ---------------------------------------------------------------------------


async def approve_refund(
    session: AsyncSession,
    *,
    record_id: uuid.UUID,
    admin_id: uuid.UUID,
    amount_usd: float | None,
    reason_note: str,
    payment_intent: str | None = None,
    charge: str | None = None,
    credit_reverse_delta: int = 0,
    request_ip: str = "system:refund",
    request_user_agent: str = "admin",
) -> RefundDecision:
    """Approve a queued refund and execute the Stripe refund."""
    row = (
        await session.execute(
            select(RefundRecord).where(RefundRecord.id == record_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise RefundError(stage="lookup", message=f"refund {record_id!r} not found")

    final_amount = (
        amount_usd if amount_usd is not None else float(row.amount_usd or 0)
    )
    amount_cents = _amount_cents(final_amount) if final_amount > 0 else None

    refund = await _stripe_create_refund(
        payment_intent=payment_intent,
        charge=charge,
        amount_cents=amount_cents,
        metadata={
            "refund_record_id": str(row.id),
            "user_id": str(row.user_id),
            "admin_id": str(admin_id),
        },
    )
    stripe_refund_id = str(refund.get("id") or "")
    if not stripe_refund_id:
        raise RefundError(stage="stripe", message="empty refund id from Stripe")

    before = {
        "stripe_refund_id": row.stripe_refund_id,
        "amount_usd": float(row.amount_usd or 0),
        "initiated_by": row.initiated_by.value
        if hasattr(row.initiated_by, "value")
        else str(row.initiated_by),
    }
    row.stripe_refund_id = stripe_refund_id
    row.amount_usd = final_amount
    row.initiated_by = RefundInitiator.admin
    row.admin_id = admin_id

    await _emit_credit_reverse(
        session,
        user_id=row.user_id,
        delta=credit_reverse_delta,
        refund_record_id=row.id,
        note=reason_note,
    )

    audit_id = await _emit_audit(
        session,
        actor_admin_id=admin_id,
        action="refund_approved",
        target_id=str(row.id),
        before=before,
        after={
            "stripe_refund_id": stripe_refund_id,
            "amount_usd": final_amount,
            "credit_reverse_delta": credit_reverse_delta,
            "reason_note": reason_note,
        },
        ip=request_ip,
        user_agent=request_user_agent,
    )

    await _send_user_notification(
        session,
        user_id=row.user_id,
        notification_type="refund_approved",
        title="Refund approved",
        body=(
            f"Your refund of ${final_amount:.2f} has been approved and "
            "should appear on your statement within 5-10 business days."
        ),
        data={
            "refund_record_id": str(row.id),
            "stripe_refund_id": stripe_refund_id,
            "amount_usd": final_amount,
            "url": "/billing",
        },
    )

    log.info(
        "billing.refund.approved",
        record_id=str(row.id),
        admin_id=str(admin_id),
        stripe_refund_id=stripe_refund_id,
        amount_usd=final_amount,
    )
    return RefundDecision(
        record_id=row.id,
        audit_id=audit_id,
        stripe_refund_id=stripe_refund_id,
    )


async def deny_refund(
    session: AsyncSession,
    *,
    record_id: uuid.UUID,
    admin_id: uuid.UUID,
    reason_note: str,
    request_ip: str = "system:refund",
    request_user_agent: str = "admin",
) -> RefundDecision:
    """Deny a queued refund and notify the user via email."""
    row = (
        await session.execute(
            select(RefundRecord).where(RefundRecord.id == record_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise RefundError(stage="lookup", message=f"refund {record_id!r} not found")

    before = {
        "stripe_refund_id": row.stripe_refund_id,
        "admin_id": str(row.admin_id) if row.admin_id else None,
    }
    if row.stripe_refund_id.startswith("pending_"):
        row.stripe_refund_id = f"denied_{uuid.uuid4().hex}"
    row.admin_id = admin_id

    audit_id = await _emit_audit(
        session,
        actor_admin_id=admin_id,
        action="refund_denied",
        target_id=str(row.id),
        before=before,
        after={
            "stripe_refund_id": row.stripe_refund_id,
            "reason_note": reason_note,
        },
        ip=request_ip,
        user_agent=request_user_agent,
    )

    await _send_user_notification(
        session,
        user_id=row.user_id,
        notification_type="refund_denied",
        title="Your refund request was declined",
        body=(
            "After reviewing your request, our team was unable to issue "
            f"a refund.  Reason: {reason_note}"
        ),
        data={
            "refund_record_id": str(row.id),
            "denial_reason": reason_note,
            "url": "/billing",
        },
    )

    log.info(
        "billing.refund.denied",
        record_id=str(row.id),
        admin_id=str(admin_id),
        reason=reason_note,
    )
    return RefundDecision(record_id=row.id, audit_id=audit_id)


async def self_service_refund(
    session: AsyncSession,
    *,
    user: User,
    amount_usd: float | None = None,
    reason_note: str = "self-service 24h",
    payment_intent: str | None = None,
    charge: str | None = None,
    credit_reverse_delta: int = 0,
    now: datetime | None = None,
    request_ip: str = "system:refund",
    request_user_agent: str = "self_service",
) -> RefundDecision:
    """24h self-service refund per §18.3 row 1.

    Eligibility check: the user's most recent subscription must have
    been created within :data:`SELF_SERVICE_WINDOW_HOURS` from ``now``.
    The route layer can pass ``now`` for tests; in production we use
    the wallclock.

    On success: creates a :class:`RefundRecord` row with
    ``initiated_by='user'`` and ``reason='self_service_24h'``, calls
    Stripe directly, optionally reverses any granted credits, and
    writes one :class:`AdminAuditLog` row with
    ``actor_admin_id=None``.
    """
    now_dt = now or datetime.now(timezone.utc)
    sub = await _latest_subscription(session, user_id=user.id)
    if sub is None:
        raise RefundError(stage="lookup", message="no subscription to refund")

    elapsed = now_dt - sub.created_at
    if elapsed.total_seconds() > SELF_SERVICE_WINDOW_HOURS * 3600:
        raise RefundError(
            stage="window",
            message="outside 24h self-service refund window",
        )

    record = RefundRecord(
        id=uuid.uuid4(),
        user_id=user.id,
        subscription_id=sub.id,
        stripe_refund_id=f"pending_{uuid.uuid4().hex}",
        amount_usd=amount_usd if amount_usd is not None else 0,
        reason=RefundReason.self_service_24h,
        initiated_by=RefundInitiator.user,
    )
    session.add(record)
    await session.flush()

    amount_cents = (
        _amount_cents(amount_usd) if amount_usd and amount_usd > 0 else None
    )
    refund = await _stripe_create_refund(
        payment_intent=payment_intent,
        charge=charge,
        amount_cents=amount_cents,
        metadata={
            "refund_record_id": str(record.id),
            "user_id": str(user.id),
            "self_service": "true",
        },
    )
    stripe_refund_id = str(refund.get("id") or "")
    if not stripe_refund_id:
        raise RefundError(stage="stripe", message="empty refund id from Stripe")
    record.stripe_refund_id = stripe_refund_id
    if amount_usd is not None:
        record.amount_usd = amount_usd

    await _emit_credit_reverse(
        session,
        user_id=user.id,
        delta=credit_reverse_delta,
        refund_record_id=record.id,
        note=reason_note,
    )

    audit_id = await _emit_audit(
        session,
        actor_admin_id=None,
        action="refund_self_service",
        target_id=str(record.id),
        before={"reason": "self_service_24h"},
        after={
            "stripe_refund_id": stripe_refund_id,
            "amount_usd": float(record.amount_usd or 0),
            "credit_reverse_delta": credit_reverse_delta,
        },
        ip=request_ip,
        user_agent=request_user_agent,
    )

    await _send_user_notification(
        session,
        user_id=user.id,
        notification_type="refund_self_service",
        title="Refund issued",
        body=(
            "Your 24-hour self-service refund has been processed and "
            "should appear on your statement within 5-10 business days."
        ),
        data={
            "refund_record_id": str(record.id),
            "stripe_refund_id": stripe_refund_id,
            "amount_usd": float(record.amount_usd or 0),
            "url": "/billing",
        },
    )

    log.info(
        "billing.refund.self_service",
        record_id=str(record.id),
        user_id=str(user.id),
        stripe_refund_id=stripe_refund_id,
    )
    return RefundDecision(
        record_id=record.id,
        audit_id=audit_id,
        stripe_refund_id=stripe_refund_id,
    )


__all__ = [
    "RefundDecision",
    "SELF_SERVICE_WINDOW_HOURS",
    "approve_refund",
    "deny_refund",
    "self_service_refund",
]
