"""Unit tests for post-merge review fixes (no DB)."""

from __future__ import annotations

from app.models.billing import SubscriptionBillingCycle, SubscriptionPlan
from app.services.admin.grants import InvalidGrantPayloadError, validate_grant_payload
from app.models.admin_grant import AdminGrantType
from app.services.billing.webhook_handler import _classify_code


def test_webhook_classifies_monthly_pro_code() -> None:
    plan, cycle, tier, llm_billing = _classify_code("monthly_pro")
    assert plan == SubscriptionPlan.monthly
    assert cycle == SubscriptionBillingCycle.recurring
    assert tier.value == "standard"
    assert llm_billing is None


def test_webhook_classifies_yearly_premium_code() -> None:
    plan, cycle, _, _ = _classify_code("yearly_premium")
    assert plan == SubscriptionPlan.monthly
    assert cycle == SubscriptionBillingCycle.yearly


def test_admin_grant_rejects_legacy_better_credits() -> None:
    try:
        validate_grant_payload(
            AdminGrantType.extra_credits,
            {"amount": 5, "credit_kind": "better"},
        )
    except InvalidGrantPayloadError as exc:
        assert "free" in str(exc)
    else:
        raise AssertionError("expected InvalidGrantPayloadError")
