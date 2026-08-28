from __future__ import annotations

# Curated model options per provider — shown in the UI picker.
# Users can still type a custom model id if needed (OpenRouter, Ollama).

MODEL_CATALOG: dict[str, list[dict[str, str]]] = {
    "openai": [
        {"id": "gpt-4o", "label": "GPT-4o", "note": "Best balance of quality and speed (recommended)"},
        {"id": "gpt-4o-mini", "label": "GPT-4o Mini", "note": "Fast and cheap — good for testing"},
        {"id": "gpt-4.1-mini", "label": "GPT-4.1 Mini", "note": "Newer mini tier"},
        {"id": "gpt-5-mini", "label": "GPT-5 Mini", "note": "Latest mini model"},
        {"id": "gpt-4-turbo", "label": "GPT-4 Turbo", "note": "Previous flagship; higher cost"},
    ],
    "anthropic": [
        {"id": "claude-3-5-sonnet-20241022", "label": "Claude 3.5 Sonnet", "note": "Best balance (recommended)"},
        {"id": "claude-3-opus-20240229", "label": "Claude 3 Opus", "note": "Highest quality, slowest"},
        {"id": "claude-3-haiku-20240307", "label": "Claude 3 Haiku", "note": "Fast and cheap"},
    ],
    "gemini": [
        {"id": "gemini-3.6-flash", "label": "Gemini 3.6 Flash", "note": "Recommended — current Flash workhorse"},
        {"id": "gemini-3.5-flash", "label": "Gemini 3.5 Flash", "note": "Previous Flash"},
        {"id": "gemini-3.5-flash-lite", "label": "Gemini 3.5 Flash-Lite", "note": "Fastest and cheapest"},
    ],
    "deepseek": [
        {"id": "deepseek-v4-flash", "label": "DeepSeek V4 Flash", "note": "Low-cost rewrite candidate"},
    ],
    "openrouter": [
        {"id": "meta-llama/llama-3.1-70b-instruct", "label": "Llama 3.1 70B", "note": "Strong open model"},
        {"id": "meta-llama/llama-3.1-8b-instruct", "label": "Llama 3.1 8B", "note": "Fast and cheap"},
        {"id": "mistralai/mixtral-8x7b-instruct", "label": "Mixtral 8x7B", "note": "Good general purpose"},
        {"id": "anthropic/claude-3.5-sonnet", "label": "Claude 3.5 Sonnet (via OpenRouter)", "note": "Anthropic via OpenRouter"},
        {"id": "openai/gpt-4o", "label": "GPT-4o (via OpenRouter)", "note": "OpenAI via OpenRouter"},
    ],
    "ollama": [
        {"id": "llama3.1:8b", "label": "Llama 3.1 8B", "note": "Fast local model (recommended)"},
        {"id": "llama3.1:70b", "label": "Llama 3.1 70B", "note": "Higher quality, needs more RAM"},
        {"id": "mistral:7b", "label": "Mistral 7B", "note": "Lightweight alternative"},
        {"id": "qwen2.5:14b", "label": "Qwen 2.5 14B", "note": "Strong coding/reasoning"},
    ],
}


def models_for_provider(provider_id: str) -> list[dict[str, str]]:
    return MODEL_CATALOG.get(provider_id, [])


def default_model_for_provider(provider_id: str) -> str:
    models = models_for_provider(provider_id)
    return models[0]["id"] if models else ""
