"""Pricing coverage guard for admin-pin models."""

from __future__ import annotations

from app.llm.model_catalog import MODEL_CATALOG
from app.llm.model_registry import STEP_DEFAULTS
from app.llm.pricing import estimate_cost, has_price_row


_ADMIN_PROVIDERS = ("openai", "anthropic", "gemini", "deepseek", "openrouter", "ollama")


def test_model_catalog_entries_have_pricing_rows() -> None:
    missing: list[str] = []
    for provider in _ADMIN_PROVIDERS:
        for entry in MODEL_CATALOG.get(provider, []):
            model_id = entry["id"]
            if not has_price_row(provider, model_id):
                missing.append(f"{provider}/{model_id}")
    assert not missing, f"Missing pricing rows: {missing}"


def test_step_defaults_have_pricing_rows() -> None:
    missing: list[str] = []
    for step, (provider, model) in STEP_DEFAULTS.items():
        if not has_price_row(provider, model):
            missing.append(f"{step} -> {provider}/{model}")
    assert not missing, f"STEP_DEFAULTS missing pricing: {missing}"


def test_estimate_cost_nonzero_for_priced_models() -> None:
    cost = estimate_cost(1000, 500, "deepseek", "deepseek-v4-flash")
    assert cost > 0.0
    cost_openai = estimate_cost(1000, 500, "openai", "gpt-4.1-mini")
    assert cost_openai > 0.0
