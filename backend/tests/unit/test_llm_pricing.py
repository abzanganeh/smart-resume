"""Regression tests for LLM cost estimation (M18 slice 1)."""

from __future__ import annotations

import logging

import pytest

from app.llm.pricing import (
    clear_recorded_pricing_gaps,
    estimate_cost,
    get_recorded_pricing_gaps,
    has_price_row,
)
from app.services.billing.tier_limits import get_seed_rows


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_pricing_gaps() -> None:
    clear_recorded_pricing_gaps()


def test_every_seed_tier_model_has_price_row() -> None:
    """Every tier's phase-3 model must resolve to a verified pricing row."""
    missing: list[str] = []
    for row in get_seed_rows():
        provider = row["llm_provider"]
        model = row["llm_model_phase3"]
        if not has_price_row(provider, model):
            missing.append(f"{row['plan_code']} -> {provider}/{model}")
    assert not missing, "Missing pricing rows: " + "; ".join(missing)


def test_claude_sonnet_4_6_has_nonzero_estimate() -> None:
    cost = estimate_cost(1_000_000, 1_000_000, "anthropic", "claude-sonnet-4-6")
    assert cost == 18.0


def test_unknown_model_logs_warning_and_records_gap(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        cost = estimate_cost(1000, 1000, "anthropic", "claude-unknown-model")
    assert cost == 0.0
    assert ("anthropic", "claude-unknown-model") in get_recorded_pricing_gaps()
    assert any("No LLM pricing row" in record.message for record in caplog.records)


def test_unknown_model_warning_is_deduped(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        estimate_cost(100, 100, "gemini", "missing-model")
        estimate_cost(200, 200, "gemini", "missing-model")
    assert len([r for r in caplog.records if "No LLM pricing row" in r.message]) == 1
