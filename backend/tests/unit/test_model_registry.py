"""Unified step→model registry (M18 slice 3)."""

from __future__ import annotations

import pytest

from app.llm import model_registry
from app.llm.model_registry import resolve_model


pytestmark = pytest.mark.unit


def test_resolve_model_returns_step_default() -> None:
    provider, model = resolve_model("phase3_rewrite")
    assert provider == "gemini"
    assert model == "gemini-2.5-flash"


def test_tier_override_wins_over_step_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        model_registry.TIER_STEP_OVERRIDES,
        "monthly_premium",
        {"phase3_rewrite": ("anthropic", "claude-sonnet-4-6")},
    )
    provider, model = resolve_model("phase3_rewrite", tier="monthly_premium")
    assert provider == "anthropic"
    assert model == "claude-sonnet-4-6"

    default_provider, default_model = resolve_model("phase3_rewrite", tier="free")
    assert (default_provider, default_model) == ("gemini", "gemini-2.5-flash")

    model_registry.TIER_STEP_OVERRIDES.pop("monthly_premium", None)
