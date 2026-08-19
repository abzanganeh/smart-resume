"""Guards the advertised plan allowances against the enforced tier limits.

Marketing copy on the billing page reads the ``limits`` block returned by
``/api/billing/prices``. If that block ever stops mirroring the tier-limits seed,
the plan cards start promising quotas the quota layer will not honour.
"""

from __future__ import annotations

import pytest

from app.services.billing.public_prices import (
    PUBLIC_PLAN_CODES,
    _public_limits_for_plan,
    display_name_for_plan_code,
)
from app.services.billing.tier_limits import seed_row_for_plan

pytestmark = pytest.mark.unit

_ADVERTISED_FIELDS = (
    "resumes_per_period",
    "searches_per_period",
    "fit_analyses_per_period",
    "whisper_uses_per_period",
    "career_watch_companies",
)


@pytest.mark.parametrize("plan_code", sorted(PUBLIC_PLAN_CODES))
def test_advertised_limits_match_enforced_seed(plan_code: str) -> None:
    limits = _public_limits_for_plan(plan_code)
    seed = seed_row_for_plan(plan_code)

    assert seed is not None, f"{plan_code} must exist in the tier-limits seed"
    assert limits is not None, f"{plan_code} must advertise limits"
    for field in _ADVERTISED_FIELDS:
        assert limits[field] == seed[field], f"{plan_code}.{field} drifted from the seed"


@pytest.mark.parametrize("plan_code", sorted(PUBLIC_PLAN_CODES))
def test_every_public_plan_has_a_marketing_label(plan_code: str) -> None:
    label = display_name_for_plan_code(plan_code)
    assert label
    # A raw code leaking into the UI is the bug this replaced.
    assert "_" not in label


def test_monthly_and_yearly_variants_share_a_label_and_limits() -> None:
    for tier in ("pro", "plus", "premium"):
        monthly, yearly = f"monthly_{tier}", f"yearly_{tier}"
        assert display_name_for_plan_code(monthly) == display_name_for_plan_code(yearly)
        assert _public_limits_for_plan(monthly) == _public_limits_for_plan(yearly)


def test_free_plan_is_not_publicly_purchasable() -> None:
    assert "free" not in PUBLIC_PLAN_CODES


def test_premium_whisper_is_uncapped_and_lower_tiers_are_not() -> None:
    for tier in ("monthly_premium", "yearly_premium"):
        limits = _public_limits_for_plan(tier)
        assert limits is not None
        assert limits["whisper_uses_per_period"] is None

    for tier in ("weekly", "monthly_pro", "monthly_plus"):
        limits = _public_limits_for_plan(tier)
        assert limits is not None
        assert limits["whisper_uses_per_period"] is not None
