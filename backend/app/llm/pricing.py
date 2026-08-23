from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Price per 1M tokens in USD (standard tier, text where applicable).
# verified 2026-08-22 — sources:
#   Gemini: https://ai.google.dev/gemini-api/docs/pricing
#   Anthropic: https://platform.claude.com/docs/en/about-claude/pricing
#   OpenAI: https://developers.openai.com/api/docs/models/gpt-4o
PRICING: dict[str, dict[str, dict[str, float]]] = {
    "openai": {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "text-embedding-3-small": {"input": 0.02, "output": 0.0},
    },
    "anthropic": {
        "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    },
    "gemini": {
        "gemini-3.6-flash": {"input": 1.50, "output": 7.50},
        "gemini-3.5-flash": {"input": 1.50, "output": 9.00},
        "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
        "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
        "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    },
    "openrouter": {
        "meta-llama/llama-3.1-70b-instruct": {"input": 0.52, "output": 0.75},
        "mistralai/mixtral-8x7b-instruct": {"input": 0.24, "output": 0.24},
    },
    "ollama": {
        # Local — no cost
        "*": {"input": 0.0, "output": 0.0},
    },
}

_recorded_pricing_gaps: set[tuple[str, str]] = set()


def has_price_row(provider: str, model: str) -> bool:
    """Return True when ``estimate_cost`` can resolve a rate for provider/model."""
    provider_prices = PRICING.get(provider, {})
    return model in provider_prices or "*" in provider_prices


def get_recorded_pricing_gaps() -> frozenset[tuple[str, str]]:
    """Return provider/model pairs that hit the unknown-pricing path."""
    return frozenset(_recorded_pricing_gaps)


def clear_recorded_pricing_gaps() -> None:
    """Reset gap tracking — for tests only."""
    _recorded_pricing_gaps.clear()


def estimate_cost(input_tokens: int, output_tokens: int, provider: str, model: str) -> float:
    """Return estimated cost in USD."""
    provider_prices = PRICING.get(provider, {})
    prices = provider_prices.get(model) or provider_prices.get("*")
    if not prices:
        gap = (provider, model)
        if gap not in _recorded_pricing_gaps:
            _recorded_pricing_gaps.add(gap)
            log.warning(
                "No LLM pricing row for provider=%s model=%s; estimate_cost returns 0.0",
                provider,
                model,
            )
        return 0.0
    cost = (input_tokens / 1_000_000) * prices["input"] + (output_tokens / 1_000_000) * prices["output"]
    return round(cost, 6)


def format_cost(cost: float) -> str:
    if cost == 0.0:
        return "Free (local)"
    if cost < 0.001:
        return f"~${cost * 100:.4f}¢"
    return f"~${cost:.4f}"
