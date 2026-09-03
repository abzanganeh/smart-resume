"""Per-plan_code step routing — tier pin → global pin → STEP_DEFAULTS."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.model_registry import STEP_DEFAULTS, resolve_model
from app.llm.step_pin_cache import clear_step_pins_for_tests, set_step_pins
from app.llm.tier_step_pin_cache import clear_tier_step_pins_for_tests, set_tier_step_pins
from app.models.llm_config import LLMProvider
from app.models.tier_step_llm_config import TierStepLLMConfig
from app.services.llm.tier_step_config import load_active_tier_step_pins, refresh_tier_step_pin_cache

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_pin_caches() -> None:
    clear_step_pins_for_tests()
    clear_tier_step_pins_for_tests()
    yield
    clear_step_pins_for_tests()
    clear_tier_step_pins_for_tests()


def test_tier_pin_wins_over_global_pin() -> None:
    set_tier_step_pins({("monthly_pro", "phase3_rewrite"): ("openai", "gpt-4o-mini")})
    set_step_pins({"phase3_rewrite": ("anthropic", "claude-sonnet-4-6")})
    provider, model = resolve_model("phase3_rewrite", plan_code="monthly_pro")
    assert provider == "openai"
    assert model == "gpt-4o-mini"


def test_global_pin_wins_when_no_tier_pin() -> None:
    set_step_pins({"phase3_rewrite": ("anthropic", "claude-sonnet-4-6")})
    provider, model = resolve_model("phase3_rewrite", plan_code="free")
    assert provider == "anthropic"
    assert model == "claude-sonnet-4-6"


def test_free_and_paid_can_differ_when_tier_pins_differ() -> None:
    set_tier_step_pins({
        ("free", "phase3_rewrite"): ("gemini", "gemini-3.5-flash-lite"),
        ("monthly_pro", "phase3_rewrite"): ("gemini", "gemini-3.5-flash"),
    })
    free_route = resolve_model("phase3_rewrite", plan_code="free")
    pro_route = resolve_model("phase3_rewrite", plan_code="monthly_pro")
    assert free_route != pro_route


def test_no_plan_code_uses_global_pin_only() -> None:
    set_tier_step_pins({("monthly_pro", "phase3_rewrite"): ("openai", "gpt-4o-mini")})
    set_step_pins({"phase3_rewrite": ("anthropic", "claude-sonnet-4-6")})
    provider, model = resolve_model("phase3_rewrite")
    assert (provider, model) == ("anthropic", "claude-sonnet-4-6")


def test_falls_back_to_step_defaults() -> None:
    provider, model = resolve_model("phase3_rewrite", plan_code="free")
    assert (provider, model) == STEP_DEFAULTS["phase3_rewrite"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tier_pin_cache_refresh_from_db(db_session: AsyncSession) -> None:
    row = TierStepLLMConfig(
        id=uuid.uuid4(),
        plan_code="monthly_pro",
        step="checkup",
        provider=LLMProvider.openai,
        model_string="gpt-4o-mini",
        is_active=True,
    )
    db_session.add(row)
    await db_session.flush()
    await refresh_tier_step_pin_cache(db_session)

    provider, model = resolve_model("checkup", plan_code="monthly_pro")
    assert provider == "openai"
    assert model == "gpt-4o-mini"

    provider, model = resolve_model("checkup", plan_code="free")
    assert (provider, model) == STEP_DEFAULTS["checkup"]
