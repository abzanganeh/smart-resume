"""Stripe webhook dispatcher — 7-event contract per IMPLEMENTATION_PLAN §7.3.

| # | Event                                  | Handler                       |
|---|----------------------------------------|-------------------------------|
| 1 | checkout.session.completed             | handle_checkout_completed     |
| 2 | customer.subscription.created          | handle_subscription_created   |
| 3 | customer.subscription.updated          | handle_subscription_updated   |
| 4 | customer.subscription.deleted          | handle_subscription_deleted   |
| 5 | invoice.payment_succeeded              | handle_invoice_succeeded      |
| 6 | invoice.payment_failed                 | handle_invoice_failed         |
| 7 | customer.subscription.trial_will_end   | handle_trial_will_end         |

Any other event type is acknowledged with 200 and logged at INFO without
business effects (router calls ``handle_unsupported_event``).

Each handler runs inside the single transaction opened by the router.
Ordering guard (§7.4): if an incoming event's ``event.created`` is
older than the target ``Subscription.last_event_created_at``, we mark
the row processed without mutation and log ``out_of_order_skip`` —
Stripe is the source of truth and retransmits, but we never let an
older event overwrite a newer state.

One-time grants (better_5pack, best_per_resume) write a
``CreditTransaction`` keyed by ``(stripe_event_id, credit_kind)`` so
double delivery becomes a no-op via the partial UNIQUE index from §7.5.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    CreditKind,
    LLMUpgradeBillingCycle,
    LLMUpgradeTier,
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.user import User
from app.services.billing.credits import grant_credit
from app.services.billing.exceptions import WebhookPayloadError
from app.services.billing.price_resolver import reverse_lookup_code

log = structlog.get_logger("billing.webhook")


# ---------------------------------------------------------------------------
# Code → Subscription field mapping (§7.1).
# ---------------------------------------------------------------------------


_CODE_TO_PLAN_CYCLE: dict[
    str, tuple[SubscriptionPlan, SubscriptionBillingCycle]
] = {
    "daily": (SubscriptionPlan.daily, SubscriptionBillingCycle.recurring),
    "weekly": (SubscriptionPlan.weekly, SubscriptionBillingCycle.recurring),
    "monthly": (SubscriptionPlan.monthly, SubscriptionBillingCycle.recurring),
    "monthly_yearly": (SubscriptionPlan.monthly, SubscriptionBillingCycle.yearly),
}


def _is_one_time_credit_code(code: str | None) -> bool:
    return code in {"better_pack", "best_per_resume"}


def _credit_kind_for_one_time(code: str) -> tuple[CreditKind, int]:
    """Return (kind, delta) for a one-time credit purchase code."""
    if code == "better_pack":
        return CreditKind.better, 5
    if code == "best_per_resume":
        return CreditKind.best, 1
    raise WebhookPayloadError(f"unknown credit-pack code: {code!r}")


def _is_addon_subscription_code(code: str | None) -> bool:
    return code in {
        "better_monthly",
        "better_yearly",
        "best_monthly",
        "best_yearly",
    }


def _addon_metadata_for(code: str) -> tuple[LLMUpgradeTier, LLMUpgradeBillingCycle]:
    if code == "better_monthly":
        return LLMUpgradeTier.better, LLMUpgradeBillingCycle.monthly
    if code == "better_yearly":
        return LLMUpgradeTier.better, LLMUpgradeBillingCycle.yearly
    if code == "best_monthly":
        return LLMUpgradeTier.best, LLMUpgradeBillingCycle.monthly
    if code == "best_yearly":
        return LLMUpgradeTier.best, LLMUpgradeBillingCycle.yearly
    raise WebhookPayloadError(f"unknown add-on code: {code!r}")


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


async def _user_for_customer(
    session: AsyncSession, *, customer_id: str | None, user_id: str | None
) -> User | None:
    """Resolve the User row from a Stripe customer id or metadata user_id.

    Checkout sets ``client_reference_id`` to ``user.id`` so the first
    event for a user is always linkable.  Subsequent events match by
    customer via the existing :class:`Subscription` row.
    """
    if user_id:
        try:
            uid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            uid = None
        if uid is not None:
            user = (
                await session.execute(select(User).where(User.id == uid))
            ).scalar_one_or_none()
            if user is not None:
                return user

    if customer_id:
        sub = (
            await session.execute(
                select(Subscription)
                .where(Subscription.stripe_customer_id == customer_id)
                .order_by(Subscription.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if sub is not None:
            return await session.get(User, sub.user_id)

    return None


async def _subscription_by_stripe_id(
    session: AsyncSession, *, stripe_subscription_id: str
) -> Subscription | None:
    return (
        await session.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id
            )
        )
    ).scalar_one_or_none()


def _ts_to_dt(ts: int | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def _event_created_at(event: dict[str, Any]) -> datetime:
    return _ts_to_dt(event.get("created")) or datetime.now(timezone.utc)


def _is_out_of_order(
    event: dict[str, Any], sub: Subscription | None
) -> bool:
    if sub is None or sub.last_event_created_at is None:
        return False
    return _event_created_at(event) < sub.last_event_created_at


# ---------------------------------------------------------------------------
# Handlers (one per event type in §7.3)
# ---------------------------------------------------------------------------


async def handle_checkout_completed(
    session: AsyncSession, event: dict[str, Any]
) -> None:
    """Event #1 — Stripe Checkout returned."""
    obj = event["data"]["object"]
    customer_id: str | None = obj.get("customer")
    metadata = obj.get("metadata") or {}
    code = metadata.get("code")

    user = await _user_for_customer(
        session,
        customer_id=customer_id,
        user_id=metadata.get("user_id") or obj.get("client_reference_id"),
    )
    if user is None:
        raise WebhookPayloadError(
            f"checkout.session.completed missing resolvable user "
            f"(customer={customer_id!r}, ref={obj.get('client_reference_id')!r})"
        )

    if code and _is_one_time_credit_code(code):
        kind, delta = _credit_kind_for_one_time(code)
        try:
            await grant_credit(
                session,
                user_id=user.id,
                credit_kind=kind,
                delta=delta,
                reason=f"purchase_{code}",
                stripe_event_id=event["id"],
            )
        except IntegrityError:
            # Partial UNIQUE on (stripe_event_id, credit_kind) — duplicate
            # delivery already granted these credits.  Roll back the
            # failed insert savepoint so the webhook row commits clean.
            await session.rollback()
            log.info(
                "billing.webhook.duplicate_credit_grant_noop",
                event_id=event["id"],
                code=code,
            )
        return

    # Recurring base plan or add-on subscription — Stripe will fire
    # ``customer.subscription.created`` next which is the authoritative
    # state-creating event (§7.3 row 2).  Nothing to do here.
    log.info(
        "billing.webhook.checkout_recurring_acknowledged",
        event_id=event["id"],
        code=code,
        user_id=str(user.id),
    )


async def handle_subscription_created(
    session: AsyncSession, event: dict[str, Any]
) -> None:
    """Event #2 — idempotent upsert of :class:`Subscription`."""
    obj = event["data"]["object"]
    stripe_sub_id = obj["id"]

    existing = await _subscription_by_stripe_id(
        session, stripe_subscription_id=stripe_sub_id
    )
    if _is_out_of_order(event, existing):
        log.info(
            "billing.webhook.out_of_order_skip",
            event_id=event["id"],
            stripe_subscription_id=stripe_sub_id,
        )
        return

    metadata = obj.get("metadata") or {}
    user = await _user_for_customer(
        session,
        customer_id=obj.get("customer"),
        user_id=metadata.get("user_id"),
    )
    if user is None:
        raise WebhookPayloadError(
            f"subscription.created missing resolvable user (id={stripe_sub_id!r})"
        )

    price_id = _first_price_id(obj)
    code = await reverse_lookup_code(session, price_id) if price_id else None

    plan, billing_cycle, llm_tier, llm_billing = _classify_code(code)

    fields = _subscription_fields_from_event(obj)

    if existing is None:
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=user.id,
            plan=plan,
            billing_cycle=billing_cycle,
            llm_upgrade=llm_tier,
            llm_upgrade_billing_cycle=llm_billing,
            stripe_customer_id=obj.get("customer", ""),
            stripe_subscription_id=stripe_sub_id,
            stripe_price_id=price_id or "",
            **fields,
            last_event_created_at=_event_created_at(event),
        )
        session.add(sub)
    else:
        existing.plan = plan
        existing.billing_cycle = billing_cycle
        existing.llm_upgrade = llm_tier
        existing.llm_upgrade_billing_cycle = llm_billing
        existing.stripe_customer_id = obj.get("customer", existing.stripe_customer_id)
        existing.stripe_price_id = price_id or existing.stripe_price_id
        for k, v in fields.items():
            setattr(existing, k, v)
        existing.last_event_created_at = _event_created_at(event)
        existing.updated_at = datetime.now(timezone.utc)

    await session.flush()


async def handle_subscription_updated(
    session: AsyncSession, event: dict[str, Any]
) -> None:
    """Event #3 — plan change, pause/resume, cancel-at-period-end toggle."""
    obj = event["data"]["object"]
    stripe_sub_id = obj["id"]
    existing = await _subscription_by_stripe_id(
        session, stripe_subscription_id=stripe_sub_id
    )
    if existing is None:
        # Stripe can send updated before created if Stripe's queue
        # reorders during high load.  Treat as out-of-order: park the
        # event and rely on a later replay or the eventual `created`.
        raise WebhookPayloadError(
            f"subscription.updated for unknown id={stripe_sub_id!r}"
        )
    if _is_out_of_order(event, existing):
        log.info(
            "billing.webhook.out_of_order_skip",
            event_id=event["id"],
            stripe_subscription_id=stripe_sub_id,
        )
        return

    fields = _subscription_fields_from_event(obj)
    for k, v in fields.items():
        setattr(existing, k, v)

    price_id = _first_price_id(obj)
    if price_id:
        existing.stripe_price_id = price_id
        code = await reverse_lookup_code(session, price_id)
        plan, billing_cycle, llm_tier, llm_billing = _classify_code(code)
        existing.plan = plan
        existing.billing_cycle = billing_cycle
        if llm_tier is not LLMUpgradeTier.standard:
            existing.llm_upgrade = llm_tier
            existing.llm_upgrade_billing_cycle = llm_billing

    existing.last_event_created_at = _event_created_at(event)
    existing.updated_at = datetime.now(timezone.utc)
    await session.flush()


async def handle_subscription_deleted(
    session: AsyncSession, event: dict[str, Any]
) -> None:
    """Event #4 — terminate subscription; preserve row for history."""
    obj = event["data"]["object"]
    stripe_sub_id = obj["id"]
    existing = await _subscription_by_stripe_id(
        session, stripe_subscription_id=stripe_sub_id
    )
    if existing is None:
        log.info(
            "billing.webhook.delete_unknown_subscription",
            event_id=event["id"],
            stripe_subscription_id=stripe_sub_id,
        )
        return
    if _is_out_of_order(event, existing):
        log.info(
            "billing.webhook.out_of_order_skip",
            event_id=event["id"],
            stripe_subscription_id=stripe_sub_id,
        )
        return
    existing.status = SubscriptionStatus.expired
    existing.ended_at = datetime.now(timezone.utc)
    existing.last_event_created_at = _event_created_at(event)
    existing.updated_at = datetime.now(timezone.utc)
    await session.flush()


async def handle_invoice_succeeded(
    session: AsyncSession, event: dict[str, Any]
) -> None:
    """Event #5 — clear grace state, restore active."""
    obj = event["data"]["object"]
    stripe_sub_id = obj.get("subscription")
    if not stripe_sub_id:
        log.info("billing.webhook.invoice_succeeded_no_subscription", event_id=event["id"])
        return
    existing = await _subscription_by_stripe_id(
        session, stripe_subscription_id=stripe_sub_id
    )
    if existing is None:
        log.info(
            "billing.webhook.invoice_unknown_subscription",
            event_id=event["id"],
            stripe_subscription_id=stripe_sub_id,
        )
        return
    if _is_out_of_order(event, existing):
        log.info(
            "billing.webhook.out_of_order_skip",
            event_id=event["id"],
            stripe_subscription_id=stripe_sub_id,
        )
        return
    if existing.status == SubscriptionStatus.grace:
        existing.status = SubscriptionStatus.active
        existing.payment_failed_at = None
    existing.last_event_created_at = _event_created_at(event)
    existing.updated_at = datetime.now(timezone.utc)
    await session.flush()


async def handle_invoice_failed(
    session: AsyncSession, event: dict[str, Any]
) -> None:
    """Event #6 — kick off / extend grace state per §7.6."""
    obj = event["data"]["object"]
    stripe_sub_id = obj.get("subscription")
    if not stripe_sub_id:
        return
    existing = await _subscription_by_stripe_id(
        session, stripe_subscription_id=stripe_sub_id
    )
    if existing is None:
        log.info(
            "billing.webhook.invoice_failed_unknown_subscription",
            event_id=event["id"],
            stripe_subscription_id=stripe_sub_id,
        )
        return
    if _is_out_of_order(event, existing):
        log.info(
            "billing.webhook.out_of_order_skip",
            event_id=event["id"],
            stripe_subscription_id=stripe_sub_id,
        )
        return
    if existing.status in {
        SubscriptionStatus.trialing,
        SubscriptionStatus.active,
        SubscriptionStatus.grace,
    }:
        existing.status = SubscriptionStatus.grace
        existing.payment_failed_at = _event_created_at(event)
    existing.last_event_created_at = _event_created_at(event)
    existing.updated_at = datetime.now(timezone.utc)
    await session.flush()


async def handle_trial_will_end(
    session: AsyncSession, event: dict[str, Any]
) -> None:
    """Event #7 — read-only signal; defer notification fan-out to Step 31."""
    obj = event["data"]["object"]
    stripe_sub_id = obj.get("id")
    if not stripe_sub_id:
        return
    existing = await _subscription_by_stripe_id(
        session, stripe_subscription_id=stripe_sub_id
    )
    if existing is None:
        return
    if _is_out_of_order(event, existing):
        log.info(
            "billing.webhook.out_of_order_skip",
            event_id=event["id"],
            stripe_subscription_id=stripe_sub_id,
        )
        return
    # No DB mutation — Step 31 (notifications) will emit the
    # in-app/email message off this audit row.
    existing.last_event_created_at = _event_created_at(event)
    await session.flush()
    log.info(
        "billing.webhook.trial_will_end_acknowledged",
        event_id=event["id"],
        stripe_subscription_id=stripe_sub_id,
    )


async def handle_unsupported_event(
    session: AsyncSession, event: dict[str, Any]
) -> None:
    """Acknowledge any other event type at INFO without business effects."""
    log.info(
        "billing.webhook.unsupported_event_ack",
        event_id=event.get("id"),
        event_type=event.get("type"),
    )


HandlerType = Callable[[AsyncSession, dict[str, Any]], Any]

EVENT_HANDLERS: dict[str, HandlerType] = {
    "checkout.session.completed": handle_checkout_completed,
    "customer.subscription.created": handle_subscription_created,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
    "invoice.payment_succeeded": handle_invoice_succeeded,
    "invoice.payment_failed": handle_invoice_failed,
    "customer.subscription.trial_will_end": handle_trial_will_end,
}


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    """Look up the handler for ``event['type']`` and invoke it.

    Unknown event types fall through to :func:`handle_unsupported_event`
    which logs and returns.  The router runs this inside a single
    transaction so any handler raising will roll back the mutation
    while the surrounding ``stripe_webhook_events`` row is updated
    separately.
    """
    handler = EVENT_HANDLERS.get(event.get("type", ""), handle_unsupported_event)
    await handler(session, event)


# ---------------------------------------------------------------------------
# Internal: extract subscription fields from a Stripe event payload.
# ---------------------------------------------------------------------------


def _classify_code(
    code: str | None,
) -> tuple[
    SubscriptionPlan,
    SubscriptionBillingCycle,
    LLMUpgradeTier,
    LLMUpgradeBillingCycle | None,
]:
    """Map a canonical code to ``(plan, billing_cycle, llm_tier, llm_billing)``.

    Add-on codes (better_*, best_*) keep the base plan/cycle defaults
    (Stripe forces a base plan on the same customer); the relevant
    information lives in the ``llm_upgrade*`` columns.  When ``code``
    is ``None`` we keep ``llm_upgrade=standard`` so the row is at
    least parseable; the next ``customer.subscription.updated`` event
    (or admin reconciliation) will refine it.
    """
    if code in _CODE_TO_PLAN_CYCLE:
        plan, cycle = _CODE_TO_PLAN_CYCLE[code]
        return plan, cycle, LLMUpgradeTier.standard, None
    if code and _is_addon_subscription_code(code):
        tier, billing = _addon_metadata_for(code)
        # Add-ons themselves don't change the *base* plan: default to
        # monthly/recurring.  When the addon is yearly, mirror that
        # (admin reconciliation aligns the base on the user account).
        cycle = (
            SubscriptionBillingCycle.yearly
            if billing == LLMUpgradeBillingCycle.yearly
            else SubscriptionBillingCycle.recurring
        )
        return SubscriptionPlan.monthly, cycle, tier, billing
    return (
        SubscriptionPlan.monthly,
        SubscriptionBillingCycle.recurring,
        LLMUpgradeTier.standard,
        None,
    )


def _first_price_id(stripe_subscription_obj: dict[str, Any]) -> str | None:
    items = (stripe_subscription_obj.get("items") or {}).get("data") or []
    if not items:
        return None
    price = items[0].get("price") or {}
    return price.get("id") if isinstance(price, dict) else getattr(price, "id", None)


def _subscription_fields_from_event(obj: dict[str, Any]) -> dict[str, Any]:
    """Translate the Stripe subscription payload into ORM-ready fields.

    Maps:
    - ``status`` (Stripe) → :class:`SubscriptionStatus` (with the §7.6
      pause / cancel_at_period_end overrides applied).
    - ``current_period_start/end`` → ``period_start/end``.
    - ``trial_end`` → ``trial_ends_at``.
    - ``cancel_at_period_end`` → ``cancel_at_period_end`` + status flip.
    - ``pause_collection`` → ``status = paused``.
    """
    stripe_status = obj.get("status", "active")
    cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
    pause_collection = obj.get("pause_collection")

    # Map Stripe → §7.6 SubscriptionStatus.
    status = _stripe_status_to_internal(stripe_status)
    if pause_collection:
        status = SubscriptionStatus.paused
    elif cancel_at_period_end and status == SubscriptionStatus.active:
        status = SubscriptionStatus.cancel_at_period_end

    return {
        "status": status,
        "trial_ends_at": _ts_to_dt(obj.get("trial_end")),
        "period_start": _ts_to_dt(obj.get("current_period_start"))
        or datetime.now(timezone.utc),
        "period_end": _ts_to_dt(obj.get("current_period_end"))
        or datetime.now(timezone.utc),
        "cancel_at_period_end": cancel_at_period_end,
        "paused_at": _ts_to_dt(
            (pause_collection or {}).get("paused_at")
        )
        if isinstance(pause_collection, dict)
        else None,
        "pause_resumes_at": _ts_to_dt(
            (pause_collection or {}).get("resumes_at")
        )
        if isinstance(pause_collection, dict)
        else None,
        "cancelled_at": _ts_to_dt(obj.get("canceled_at")),
    }


_STRIPE_STATUS_MAP: dict[str, SubscriptionStatus] = {
    "trialing": SubscriptionStatus.trialing,
    "active": SubscriptionStatus.active,
    "past_due": SubscriptionStatus.grace,
    "unpaid": SubscriptionStatus.grace,
    "paused": SubscriptionStatus.paused,
    "canceled": SubscriptionStatus.expired,
    "incomplete": SubscriptionStatus.trialing,
    "incomplete_expired": SubscriptionStatus.expired,
}


def _stripe_status_to_internal(s: str) -> SubscriptionStatus:
    return _STRIPE_STATUS_MAP.get(s, SubscriptionStatus.active)


__all__ = [
    "EVENT_HANDLERS",
    "dispatch",
    "handle_checkout_completed",
    "handle_invoice_failed",
    "handle_invoice_succeeded",
    "handle_subscription_created",
    "handle_subscription_deleted",
    "handle_subscription_updated",
    "handle_trial_will_end",
    "handle_unsupported_event",
]
