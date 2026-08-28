"""Regression tests for free-tier lifetime AI spend cap."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.llm.base import LLMMessage, LLMResponse
from app.llm.token_accounting import llm_accounting_context, record_llm_response
from app.llm.tracking_client import TrackingLLMClient
from app.services.billing.exceptions import FreeTierAiBudgetExceededError
from app.services.billing.free_tier_budget import (
    add_user_lifetime_usd,
    assert_free_user_llm_allowed,
    clear_user_lifetime_usd_for_tests,
    get_user_lifetime_usd,
)


class _FakeLLMClient:
    provider_name = "gemini"
    model_name = "gemini-3.5-flash"
    context_window = 1_000_000
    supports_structured_output = True

    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(
            content="ok",
            input_tokens=100,
            output_tokens=50,
            model=self.model_name,
            provider=self.provider_name,
        )


@pytest.mark.asyncio
async def test_lifetime_usd_accumulates_in_redis() -> None:
    user_id = str(uuid.uuid4())
    await clear_user_lifetime_usd_for_tests(user_id)
    assert await get_user_lifetime_usd(user_id) == 0.0
    total = await add_user_lifetime_usd(user_id, 0.01)
    assert total == pytest.approx(0.01)
    total = await add_user_lifetime_usd(user_id, 0.02)
    assert total == pytest.approx(0.03)
    await clear_user_lifetime_usd_for_tests(user_id)


@pytest.mark.asyncio
async def test_assert_free_user_blocks_at_cap() -> None:
    user_id = str(uuid.uuid4())
    await clear_user_lifetime_usd_for_tests(user_id)
    cap = settings.FREE_TIER_MAX_USD
    await add_user_lifetime_usd(user_id, cap)

    with patch(
        "app.services.billing.free_tier_budget._active_subscription",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(FreeTierAiBudgetExceededError):
            await assert_free_user_llm_allowed(user_id)

    await clear_user_lifetime_usd_for_tests(user_id)


@pytest.mark.asyncio
async def test_assert_free_user_skips_paid_subscribers() -> None:
    user_id = str(uuid.uuid4())
    await add_user_lifetime_usd(user_id, settings.FREE_TIER_MAX_USD)

    with patch(
        "app.services.billing.free_tier_budget._active_subscription",
        new=AsyncMock(return_value=object()),
    ):
        await assert_free_user_llm_allowed(user_id)

    await clear_user_lifetime_usd_for_tests(user_id)


@pytest.mark.asyncio
async def test_tracking_client_blocks_before_provider_call() -> None:
    user_id = str(uuid.uuid4())
    await clear_user_lifetime_usd_for_tests(user_id)
    await add_user_lifetime_usd(user_id, settings.FREE_TIER_MAX_USD)

    client = TrackingLLMClient(_FakeLLMClient())
    with patch(
        "app.services.billing.free_tier_budget._active_subscription",
        new=AsyncMock(return_value=None),
    ):
        with llm_accounting_context(user_id=user_id, step="phase3"):
            with pytest.raises(FreeTierAiBudgetExceededError):
                await client.complete([LLMMessage(role="user", content="hi")])

    await clear_user_lifetime_usd_for_tests(user_id)


@pytest.mark.asyncio
async def test_record_llm_response_increments_lifetime_for_free_users() -> None:
    user_id = str(uuid.uuid4())
    await clear_user_lifetime_usd_for_tests(user_id)

    with patch(
        "app.llm.token_accounting._append_record",
        new=AsyncMock(return_value=[]),
    ):
        with patch(
            "app.services.billing.free_tier_budget.user_on_paid_plan",
            new=AsyncMock(return_value=False),
        ):
            with llm_accounting_context(user_id=user_id, step="phase1"):
                await record_llm_response(
                    LLMResponse(
                        content="x",
                        input_tokens=1000,
                        output_tokens=500,
                        model="gemini-3.5-flash",
                        provider="gemini",
                    )
                )

    lifetime = await get_user_lifetime_usd(user_id)
    assert lifetime > 0
    await clear_user_lifetime_usd_for_tests(user_id)


_BACKEND = Path(__file__).resolve().parents[2]


def test_phase_accounting_context_binds_session_user() -> None:
    src = (_BACKEND / "app" / "agent" / "orchestrator.py").read_text(encoding="utf-8")
    assert "llm_accounting_context(" in src
    assert "user_id=session.user_id" in src
    assert 'f"phase{phase}"' in src


def test_resume_parse_and_fixes_bind_session_user() -> None:
    src = (_BACKEND / "app" / "routers" / "resume.py").read_text(encoding="utf-8")
    assert src.count("user_id=session.user_id") >= 3


def test_company_intel_extraction_forwards_user_id() -> None:
    extractor = (_BACKEND / "app" / "services" / "company_intel" / "extractor.py").read_text(
        encoding="utf-8"
    )
    assert "user_id=user_id" in extractor
    init = (_BACKEND / "app" / "services" / "company_intel" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert "user_id=session.user_id" in init
