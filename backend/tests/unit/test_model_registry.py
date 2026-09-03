"""Unified step→model registry (M18 slice 3)."""

from __future__ import annotations

import pytest

from app.llm.model_registry import (
    GLOBAL_ONLY_STEPS,
    resolve_model,
    tier_step_is_editable,
    tier_step_lock_reason,
)
from app.llm.tier_step_pin_cache import clear_tier_step_pins_for_tests, set_tier_step_pins

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_tier_pins() -> None:
    clear_tier_step_pins_for_tests()
    yield
    clear_tier_step_pins_for_tests()


def test_resolve_model_returns_step_default() -> None:
    provider, model = resolve_model("phase3_rewrite")
    assert provider == "gemini"
    assert model == "gemini-3.5-flash"


def test_plan_code_tier_pin_wins_over_step_default() -> None:
    set_tier_step_pins({
        ("monthly_premium", "phase3_rewrite"): ("anthropic", "claude-sonnet-4-6"),
    })
    provider, model = resolve_model("phase3_rewrite", plan_code="monthly_premium")
    assert provider == "anthropic"
    assert model == "claude-sonnet-4-6"

    default_provider, default_model = resolve_model("phase3_rewrite", plan_code="free")
    assert (default_provider, default_model) == ("gemini", "gemini-3.5-flash")


def test_company_intel_is_global_only_not_tier_editable() -> None:
    assert "company_intel" in GLOBAL_ONLY_STEPS
    assert tier_step_lock_reason("company_intel") == "global_only"
    assert not tier_step_is_editable("company_intel")
