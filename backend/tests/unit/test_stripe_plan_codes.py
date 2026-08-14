"""Unit tests for pricing restructure PlanConfig canonical codes (slice 3)."""

from __future__ import annotations

import pytest

from app.services.billing.bootstrap import _ELIGIBILITY_BY_CODE, _INTERVAL_BY_CODE
from app.services.billing.price_resolver import CANONICAL_CODES, ENV_VAR_BY_CODE


_NEW_BASE_PLAN_CODES = (
    "weekly",
    "monthly_pro",
    "yearly_pro",
    "monthly_plus",
    "yearly_plus",
    "monthly_premium",
    "yearly_premium",
)

_DROPPED_CODES = ("daily", "monthly", "monthly_yearly")


def test_daily_not_in_canonical_codes() -> None:
    assert "daily" not in CANONICAL_CODES


def test_legacy_monthly_codes_not_in_canonical_codes() -> None:
    for code in ("monthly", "monthly_yearly"):
        assert code not in CANONICAL_CODES


def test_pro_plus_premium_codes_in_canonical_codes() -> None:
    for code in _NEW_BASE_PLAN_CODES:
        assert code in CANONICAL_CODES


def test_each_canonical_code_has_env_var_mapping() -> None:
    for code in CANONICAL_CODES:
        assert code in ENV_VAR_BY_CODE
        assert ENV_VAR_BY_CODE[code].startswith("STRIPE_PRICE_")


def test_dropped_codes_have_no_env_var_mapping() -> None:
    for code in _DROPPED_CODES:
        assert code not in ENV_VAR_BY_CODE


def test_new_base_plans_map_to_base_plan_eligibility() -> None:
    for code in _NEW_BASE_PLAN_CODES:
        assert _ELIGIBILITY_BY_CODE[code] == "base_plan"


def test_new_base_plans_have_interval_mappings() -> None:
    from app.models.billing import PlanConfigInterval

    assert _INTERVAL_BY_CODE["weekly"] == PlanConfigInterval.week
    assert _INTERVAL_BY_CODE["monthly_pro"] == PlanConfigInterval.month
    assert _INTERVAL_BY_CODE["yearly_pro"] == PlanConfigInterval.year
    assert _INTERVAL_BY_CODE["monthly_plus"] == PlanConfigInterval.month
    assert _INTERVAL_BY_CODE["yearly_plus"] == PlanConfigInterval.year
    assert _INTERVAL_BY_CODE["monthly_premium"] == PlanConfigInterval.month
    assert _INTERVAL_BY_CODE["yearly_premium"] == PlanConfigInterval.year


@pytest.mark.parametrize("code", _NEW_BASE_PLAN_CODES)
def test_env_price_for_resolves_new_codes(
    monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    """Each new base plan code maps to a settings attribute via ENV_VAR_BY_CODE."""
    from app.config import settings
    from app.services.billing.price_resolver import _env_price_for

    env_key = ENV_VAR_BY_CODE[code]
    monkeypatch.setattr(settings, env_key, f"price_{code}_test")
    assert _env_price_for(code) == f"price_{code}_test"
