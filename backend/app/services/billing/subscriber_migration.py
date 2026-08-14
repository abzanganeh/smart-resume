"""One-off subscriber migration for the 2026 pricing restructure (slice 10).

Maps legacy base plans to canonical ``plan_configs`` codes:

- ``daily`` → ``weekly`` (updates ``subscription.plan`` and ``stripe_price_id``)
- ``monthly`` + recurring → ``monthly_pro``
- ``monthly`` + yearly → ``yearly_pro``

Expires legacy LLM add-on subscriptions (``llm_upgrade != standard``) and
zeros ``better`` / ``best`` credit balances via ledger reversals.

Run via ``backend/scripts/migrate_subscribers.py``.  Default is dry-run;
pass ``--apply`` to commit DB changes.  Optional ``--sync-stripe`` pushes
price changes to Stripe (requires ``STRIPE_SECRET_KEY``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import (
    CreditKind,
    LLMUpgradeTier,
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.user import CreditTransaction, CreditTransactionAction
from app.services.billing.credits import get_balance
from app.services.billing.price_resolver import resolve_price_id

log = structlog.get_logger("billing.subscriber_migration")

_ENTITLED_STATUSES = (
    SubscriptionStatus.active,
    SubscriptionStatus.trialing,
    SubscriptionStatus.grace,
    SubscriptionStatus.cancel_at_period_end,
)

_EXPIRE_CREDIT_REASON = "pricing_restructure_expire_addon"


@dataclass(slots=True)
class MigrationStats:
    base_plans_updated: int = 0
    daily_to_weekly: int = 0
    monthly_to_pro: int = 0
    addons_expired: int = 0
    credits_expired: int = 0
    skipped_already_migrated: int = 0
    stripe_synced: int = 0
    stripe_errors: list[str] = field(default_factory=list)


def is_addon_subscription(sub: Subscription) -> bool:
    return sub.llm_upgrade != LLMUpgradeTier.standard


def target_plan_config_code(sub: Subscription) -> str | None:
    """Return the canonical ``plan_configs.code`` for a base subscription."""
    if is_addon_subscription(sub):
        return None
    if sub.plan == SubscriptionPlan.daily:
        return "weekly"
    if sub.plan == SubscriptionPlan.weekly:
        return "weekly"
    if sub.plan == SubscriptionPlan.monthly:
        if sub.billing_cycle == SubscriptionBillingCycle.yearly:
            return "yearly_pro"
        return "monthly_pro"
    return None


async def _stripe_subscription_retrieve(stripe_subscription_id: str) -> dict[str, Any]:
    import stripe

    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY
    return await _run_stripe(
        stripe.Subscription.retrieve,
        stripe_subscription_id,
        expand=["items.data.price"],
    )


async def _stripe_subscription_modify(
    stripe_subscription_id: str,
    *,
    subscription_item_id: str,
    new_price_id: str,
) -> dict[str, Any]:
    import stripe

    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY
    return await _run_stripe(
        stripe.Subscription.modify,
        stripe_subscription_id,
        items=[{"id": subscription_item_id, "price": new_price_id}],
        proration_behavior="none",
    )


async def _run_stripe(fn: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    import asyncio

    return await asyncio.to_thread(fn, *args, **kwargs)


async def _sync_stripe_price(
    sub: Subscription,
    *,
    new_price_id: str,
    stats: MigrationStats,
) -> None:
    try:
        stripe_sub = await _stripe_subscription_retrieve(sub.stripe_subscription_id)
        items = stripe_sub.get("items", {}).get("data", [])
        if not items:
            stats.stripe_errors.append(
                f"{sub.stripe_subscription_id}: no subscription items"
            )
            return
        item_id = items[0]["id"]
        current_price = items[0].get("price", {}).get("id")
        if current_price == new_price_id:
            return
        await _stripe_subscription_modify(
            sub.stripe_subscription_id,
            subscription_item_id=item_id,
            new_price_id=new_price_id,
        )
        stats.stripe_synced += 1
    except Exception as exc:  # noqa: BLE001 — collect and continue migration
        stats.stripe_errors.append(f"{sub.stripe_subscription_id}: {exc}")
        log.warning(
            "subscriber_migration_stripe_sync_failed",
            subscription_id=str(sub.id),
            stripe_subscription_id=sub.stripe_subscription_id,
            error=str(exc),
        )


async def _expire_addon_subscription(
    session: AsyncSession,
    sub: Subscription,
    *,
    now: datetime,
    dry_run: bool,
    stats: MigrationStats,
) -> None:
    stats.addons_expired += 1
    if dry_run:
        return
    sub.status = SubscriptionStatus.expired
    sub.ended_at = now
    sub.llm_upgrade = LLMUpgradeTier.standard
    sub.llm_upgrade_billing_cycle = None
    await session.flush()


async def _migrate_base_subscription(
    session: AsyncSession,
    sub: Subscription,
    *,
    dry_run: bool,
    sync_stripe: bool,
    stats: MigrationStats,
) -> None:
    code = target_plan_config_code(sub)
    if code is None:
        return

    new_price_id = await resolve_price_id(session, code)
    plan_update_needed = sub.plan == SubscriptionPlan.daily and code == "weekly"
    price_update_needed = sub.stripe_price_id != new_price_id

    if not plan_update_needed and not price_update_needed:
        stats.skipped_already_migrated += 1
        return

    if code == "weekly" and sub.plan == SubscriptionPlan.daily:
        stats.daily_to_weekly += 1
    elif code in {"monthly_pro", "yearly_pro"}:
        stats.monthly_to_pro += 1

    stats.base_plans_updated += 1
    if dry_run:
        return

    if plan_update_needed:
        sub.plan = SubscriptionPlan.weekly
    if price_update_needed:
        sub.stripe_price_id = new_price_id
    await session.flush()

    if sync_stripe and price_update_needed and settings.STRIPE_SECRET_KEY:
        await _sync_stripe_price(sub, new_price_id=new_price_id, stats=stats)


async def _expire_addon_credits(
    session: AsyncSession,
    *,
    dry_run: bool,
    stats: MigrationStats,
) -> None:
    user_ids = (
        await session.execute(
            select(distinct(CreditTransaction.user_id)).where(
                CreditTransaction.credit_kind.in_(
                    [CreditKind.better, CreditKind.best]
                )
            )
        )
    ).scalars().all()

    for user_id in user_ids:
        for credit_kind in (CreditKind.better, CreditKind.best):
            balance = await get_balance(
                session, user_id=user_id, credit_kind=credit_kind, for_share=False
            )
            if balance <= 0:
                continue
            stats.credits_expired += 1
            if dry_run:
                continue
            session.add(
                CreditTransaction(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    delta=-balance,
                    action=CreditTransactionAction.admin_revoke,
                    reason=_EXPIRE_CREDIT_REASON,
                    credit_kind=credit_kind,
                    note="Pricing restructure: LLM add-on credits expired",
                )
            )
    if not dry_run:
        await session.flush()


async def run_subscriber_migration(
    session: AsyncSession,
    *,
    dry_run: bool = True,
    sync_stripe: bool = False,
    now: datetime | None = None,
) -> MigrationStats:
    """Migrate entitled subscriptions and expire legacy LLM add-ons."""
    now = now or datetime.now(timezone.utc)
    stats = MigrationStats()

    subs = list(
        (
            await session.execute(
                select(Subscription)
                .where(Subscription.status.in_(_ENTITLED_STATUSES))
                .order_by(Subscription.created_at.asc())
                .with_for_update()
            )
        ).scalars()
    )

    for sub in subs:
        if is_addon_subscription(sub):
            await _expire_addon_subscription(
                session, sub, now=now, dry_run=dry_run, stats=stats
            )
        else:
            await _migrate_base_subscription(
                session,
                sub,
                dry_run=dry_run,
                sync_stripe=sync_stripe,
                stats=stats,
            )

    await _expire_addon_credits(session, dry_run=dry_run, stats=stats)

    log.info(
        "subscriber_migration_complete",
        dry_run=dry_run,
        sync_stripe=sync_stripe,
        base_plans_updated=stats.base_plans_updated,
        daily_to_weekly=stats.daily_to_weekly,
        monthly_to_pro=stats.monthly_to_pro,
        addons_expired=stats.addons_expired,
        credits_expired=stats.credits_expired,
        skipped_already_migrated=stats.skipped_already_migrated,
        stripe_synced=stats.stripe_synced,
        stripe_errors=len(stats.stripe_errors),
    )
    return stats


__all__ = [
    "MigrationStats",
    "is_addon_subscription",
    "run_subscriber_migration",
    "target_plan_config_code",
]
