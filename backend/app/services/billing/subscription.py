"""Stripe checkout / portal / pause / resume / change-plan wrappers.

All persistent state changes happen via the webhook handler — these
functions never optimistically update :class:`Subscription`.  They
return the Stripe object the caller needs (Checkout URL, Portal URL,
updated subscription dict) and rely on Stripe to fire the corresponding
``customer.subscription.*`` event which then drives the DB change.

Tests stub ``stripe.checkout.Session.create`` / ``stripe.Subscription.*``
with monkeypatch; production calls are made via the official ``stripe``
Python SDK.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import stripe
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import (
    Subscription,
    SubscriptionStatus,
)
from app.models.user import User
from app.services.billing.exceptions import (
    BillingCycleMismatchError,
)
from app.services.billing.price_resolver import resolve_price_id

log = structlog.get_logger("billing.subscription")


def _configure_stripe() -> None:
    """Apply settings to the global ``stripe`` SDK once per process.

    The SDK reads ``stripe.api_key`` lazily, so it's safe to call this
    function at the top of every wrapper.  In tests where the secret
    key is empty we still configure the SDK so unit tests that
    monkeypatch ``stripe.checkout.Session.create`` etc. don't fail
    because of a missing key.
    """
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY


# ---------------------------------------------------------------------------
# Checkout / Portal
# ---------------------------------------------------------------------------


async def create_checkout_session(
    session: AsyncSession,
    *,
    user: User,
    code: str,
    success_url: str,
    cancel_url: str,
    mode: str | None = None,
) -> dict[str, Any]:
    """Create a Stripe Checkout session for ``code``.

    Returns the dict-form of ``stripe.checkout.Session`` (we keep the
    raw form rather than a Pydantic model so the router can return the
    URL straight to the client).
    """
    _configure_stripe()
    price_id = await resolve_price_id(session, code)

    # Choose mode based on the canonical code: one-time codes use
    # ``payment``, recurring codes use ``subscription``.  The caller
    # may force a mode for tests / future product types.
    if mode is None:
        mode = (
            "payment"
            if code in {"better_pack", "best_per_resume"}
            else "subscription"
        )

    metadata = {
        "user_id": str(user.id),
        "code": code,
    }

    checkout = await _run_in_thread(
        stripe.checkout.Session.create,
        mode=mode,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(user.id),
        customer_email=user.email,
        metadata=metadata,
        subscription_data=({"metadata": metadata} if mode == "subscription" else None),
        payment_intent_data=(
            {"metadata": metadata} if mode == "payment" else None
        ),
    )
    return _to_dict(checkout)


async def create_portal_session(
    session: AsyncSession,
    *,
    user: User,
    return_url: str,
) -> dict[str, Any]:
    """Create a Stripe Billing Portal session for managing cards / invoices."""
    _configure_stripe()
    sub = await _latest_subscription_for(session, user_id=user.id)
    if sub is None:
        raise ValueError("user has no Stripe customer to portal into")

    portal = await _run_in_thread(
        stripe.billing_portal.Session.create,
        customer=sub.stripe_customer_id,
        return_url=return_url,
    )
    return _to_dict(portal)


# ---------------------------------------------------------------------------
# Cancel / Resume
# ---------------------------------------------------------------------------


async def cancel_at_period_end(
    session: AsyncSession,
    *,
    user: User,
) -> dict[str, Any]:
    """Flip ``cancel_at_period_end=true`` on Stripe; webhook updates DB."""
    _configure_stripe()
    sub = await _entitled_subscription_for(session, user_id=user.id)
    if sub is None:
        raise ValueError("no entitled subscription to cancel")
    updated = await _run_in_thread(
        stripe.Subscription.modify,
        sub.stripe_subscription_id,
        cancel_at_period_end=True,
    )
    return _to_dict(updated)


async def resume_subscription(
    session: AsyncSession,
    *,
    user: User,
) -> dict[str, Any]:
    """Un-cancel a subscription that was previously set to cancel-at-period-end."""
    _configure_stripe()
    sub = await _entitled_subscription_for(session, user_id=user.id)
    if sub is None:
        raise ValueError("no entitled subscription to resume")
    updated = await _run_in_thread(
        stripe.Subscription.modify,
        sub.stripe_subscription_id,
        cancel_at_period_end=False,
    )
    return _to_dict(updated)


# ---------------------------------------------------------------------------
# Change plan
# ---------------------------------------------------------------------------


async def change_plan(
    session: AsyncSession,
    *,
    user: User,
    new_code: str,
    proration_behavior: str = "create_prorations",
) -> dict[str, Any]:
    """Switch the active subscription to a new price / plan."""
    _configure_stripe()
    sub = await _entitled_subscription_for(session, user_id=user.id)
    if sub is None:
        raise ValueError("no entitled subscription to change-plan")
    new_price_id = await resolve_price_id(session, new_code)
    item_id = await _first_subscription_item_id(sub.stripe_subscription_id)
    updated = await _run_in_thread(
        stripe.Subscription.modify,
        sub.stripe_subscription_id,
        items=[{"id": item_id, "price": new_price_id}],
        proration_behavior=proration_behavior,
    )
    return _to_dict(updated)


# ---------------------------------------------------------------------------
# Pause / Unpause
# ---------------------------------------------------------------------------


async def pause_subscription(
    session: AsyncSession,
    *,
    user: User,
    days: int,
) -> dict[str, Any]:
    """Activate Stripe pause_collection for a fixed window (§7.7).

    The 7-day minimum and 90-day maximum are enforced here so we never
    submit an invalid request to Stripe.
    """
    _configure_stripe()
    if (
        days < settings.SUBSCRIPTION_PAUSE_MIN_DAYS
        or days > settings.SUBSCRIPTION_PAUSE_MAX_DAYS
    ):
        raise ValueError(
            f"pause days must be between "
            f"{settings.SUBSCRIPTION_PAUSE_MIN_DAYS} and "
            f"{settings.SUBSCRIPTION_PAUSE_MAX_DAYS}"
        )
    sub = await _entitled_subscription_for(session, user_id=user.id)
    if sub is None:
        raise ValueError("no entitled subscription to pause")
    resume_at = int(
        (
            datetime.now(timezone.utc).timestamp()
            + days * 86400
        )
    )
    updated = await _run_in_thread(
        stripe.Subscription.modify,
        sub.stripe_subscription_id,
        pause_collection={
            "behavior": "void",
            "resumes_at": resume_at,
        },
    )
    return _to_dict(updated)


async def unpause_subscription(
    session: AsyncSession,
    *,
    user: User,
) -> dict[str, Any]:
    _configure_stripe()
    sub = await _latest_subscription_for(session, user_id=user.id)
    if sub is None:
        raise ValueError("no subscription to unpause")
    updated = await _run_in_thread(
        stripe.Subscription.modify,
        sub.stripe_subscription_id,
        pause_collection="",
    )
    return _to_dict(updated)


# ---------------------------------------------------------------------------
# LLM upgrade gating helper (used by Step 19's checkout route)
# ---------------------------------------------------------------------------


def assert_yearly_addon_alignment(
    *,
    addon_code: str,
    base_subscription: Subscription | None,
) -> None:
    """Reject yearly LLM add-ons when the base plan is monthly (§7.7).

    Raises :class:`BillingCycleMismatchError` (HTTP 409) which the
    router translates to ``billing_cycle_mismatch``.
    """
    yearly_addons = {"better_yearly", "best_yearly"}
    if addon_code not in yearly_addons:
        return
    if (
        base_subscription is None
        or base_subscription.billing_cycle.value != "yearly"
    ):
        raise BillingCycleMismatchError(
            "yearly LLM add-on requires a yearly base plan"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _latest_subscription_for(
    session: AsyncSession, *, user_id: uuid.UUID
) -> Subscription | None:
    stmt = (
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _entitled_subscription_for(
    session: AsyncSession, *, user_id: uuid.UUID
) -> Subscription | None:
    stmt = (
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .where(
            Subscription.status.in_(
                [
                    SubscriptionStatus.active,
                    SubscriptionStatus.trialing,
                    SubscriptionStatus.grace,
                    SubscriptionStatus.cancel_at_period_end,
                ]
            )
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _first_subscription_item_id(stripe_subscription_id: str) -> str:
    sub = await _run_in_thread(
        stripe.Subscription.retrieve, stripe_subscription_id
    )
    items = getattr(sub, "items", None) or {}
    data = getattr(items, "data", None) or items.get("data", [])
    if not data:
        raise ValueError("subscription has no items")
    first = data[0]
    return getattr(first, "id", None) or first["id"]


def _to_dict(obj: Any) -> dict[str, Any]:
    """Convert a stripe object to a plain dict (handles both real and stubbed)."""
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return obj
    return {"raw": str(obj)}


async def _run_in_thread(fn, *args, **kwargs):
    """Run a sync Stripe SDK call without blocking the event loop.

    The stripe-python SDK is synchronous; awaiting in-place would
    serialise on a single thread.  We delegate to the default executor
    via ``asyncio.to_thread``.
    """
    import asyncio

    # Strip any None kwargs Stripe doesn't accept.
    clean_kwargs = {k: v for k, v in kwargs.items() if v is not None}
    return await asyncio.to_thread(fn, *args, **clean_kwargs)


__all__ = [
    "assert_yearly_addon_alignment",
    "cancel_at_period_end",
    "change_plan",
    "create_checkout_session",
    "create_portal_session",
    "pause_subscription",
    "resume_subscription",
    "unpause_subscription",
]
