"""Admin per-step LLM pins — cache, seed, and resolve_model precedence."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.model_registry import STEP_DEFAULTS, resolve_model
from app.llm.step_pin_cache import clear_step_pins_for_tests, set_step_pins
from app.models.llm_config import LLMProvider
from app.models.step_llm_config import StepLLMConfig
from app.services.llm.step_config import (
    load_active_step_pins,
    refresh_step_pin_cache,
    seed_step_llm_configs_if_empty,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_pin_cache() -> None:
    clear_step_pins_for_tests()
    yield
    clear_step_pins_for_tests()


def test_resolve_model_uses_admin_pin_cache() -> None:
    set_step_pins({"phase3_rewrite": ("openai", "gpt-4o-mini")})
    provider, model = resolve_model("phase3_rewrite")
    assert provider == "openai"
    assert model == "gpt-4o-mini"


def test_resolve_model_falls_back_to_step_defaults() -> None:
    provider, model = resolve_model("phase3_rewrite")
    assert (provider, model) == STEP_DEFAULTS["phase3_rewrite"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_step_llm_configs_if_empty(db_session: AsyncSession) -> None:
    inserted = await seed_step_llm_configs_if_empty(db_session)
    assert inserted == len(STEP_DEFAULTS)

    again = await seed_step_llm_configs_if_empty(db_session)
    assert again == 0

    provider, model = resolve_model("cover_letter")
    assert (provider, model) == STEP_DEFAULTS["cover_letter"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_pin_overrides_default_after_cache_refresh(
    db_session: AsyncSession,
) -> None:
    await seed_step_llm_configs_if_empty(db_session)

    prior = (
        await db_session.execute(
            select(StepLLMConfig)
            .where(StepLLMConfig.step == "chat")
            .where(StepLLMConfig.is_active.is_(True))
        )
    ).scalar_one()
    prior.is_active = False

    row = StepLLMConfig(
        id=uuid.uuid4(),
        step="chat",
        provider=LLMProvider.openai,
        model_string="gpt-4o-mini",
        is_active=True,
    )
    db_session.add(row)
    await db_session.flush()
    await refresh_step_pin_cache(db_session)

    provider, model = resolve_model("chat")
    assert provider == "openai"
    assert model == "gpt-4o-mini"
