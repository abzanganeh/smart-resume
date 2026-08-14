"""Map a :class:`Subscription` row to a canonical ``plan_code`` string."""

from __future__ import annotations

from app.models.billing import (
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
)

# Legacy ``subscription_plan`` enum values before subscriber migration (slice 10).
_LEGACY_PLAN_CODE: dict[tuple[SubscriptionPlan, SubscriptionBillingCycle], str] = {
    (SubscriptionPlan.weekly, SubscriptionBillingCycle.recurring): "weekly",
    (SubscriptionPlan.daily, SubscriptionBillingCycle.recurring): "weekly",
    (SubscriptionPlan.monthly, SubscriptionBillingCycle.recurring): "monthly_pro",
    (SubscriptionPlan.monthly, SubscriptionBillingCycle.yearly): "yearly_pro",
}


def resolve_plan_code_for_subscription(
    sub: Subscription,
    *,
    plan_config_code: str | None,
) -> str:
    """Resolve tier-limits ``plan_code`` for an entitled subscription."""
    if plan_config_code:
        return plan_config_code
    key = (sub.plan, sub.billing_cycle)
    return _LEGACY_PLAN_CODE.get(key, "monthly_pro")


__all__ = ["resolve_plan_code_for_subscription"]
