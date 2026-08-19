from __future__ import annotations

# Price per 1M tokens in USD. Edit these to stay current.
PRICING: dict[str, dict[str, dict[str, float]]] = {
    "openai": {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    },
    "anthropic": {
        "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
        "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    },
    "gemini": {
        "gemini-3.6-flash": {"input": 1.50, "output": 7.50},
        "gemini-3.5-flash": {"input": 0.15, "output": 0.60},
        "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
        "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-2.5-flash-lite": {"input": 0.0375, "output": 0.15},
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


def estimate_cost(input_tokens: int, output_tokens: int, provider: str, model: str) -> float:
    """Return estimated cost in USD."""
    provider_prices = PRICING.get(provider, {})
    prices = provider_prices.get(model) or provider_prices.get("*")
    if not prices:
        return 0.0
    cost = (input_tokens / 1_000_000) * prices["input"] + (output_tokens / 1_000_000) * prices["output"]
    return round(cost, 6)


def format_cost(cost: float) -> str:
    if cost == 0.0:
        return "Free (local)"
    if cost < 0.001:
        return f"~${cost * 100:.4f}¢"
    return f"~${cost:.4f}"
