from __future__ import annotations

from app.config import settings
from app.llm.base import LLMClient
from app.llm.model_catalog import default_model_for_provider, models_for_provider


def _is_real_api_key(key: str) -> bool:
    """Ignore placeholder values from .env.example (e.g. sk-..., sk-ant-...)."""
    if not key or len(key) < 20:
        return False
    if "..." in key:
        return False
    return True


def has_platform_extraction_key() -> bool:
    """True when a platform-owned key exists for cheap background extraction."""
    return _is_real_api_key(settings.GOOGLE_API_KEY) or _is_real_api_key(settings.OPENAI_API_KEY)


def _get_default_key(provider: str) -> str:
    """Return the .env key for a provider (may be empty/placeholder)."""
    match provider:
        case "openai":
            return settings.OPENAI_API_KEY
        case "anthropic":
            return settings.ANTHROPIC_API_KEY
        case "gemini":
            return settings.GOOGLE_API_KEY
        case "openrouter":
            return settings.OPENROUTER_API_KEY
        case _:
            return ""


def get_llm_client(
    provider: str | None = None,
    model: str | None = None,
) -> LLMClient:
    """
    Resolve and return the configured LLM provider adapter.

    Uses platform API keys from environment / Secrets Manager for the active provider.
    """
    p = provider or settings.LLM_PROVIDER
    m = model or settings.LLM_MODEL
    key = _get_default_key(p)

    match p:
        case "openai":
            from app.llm.providers.openai_adapter import OpenAIAdapter
            return OpenAIAdapter(model=m, api_key=key)
        case "anthropic":
            from app.llm.providers.anthropic_adapter import AnthropicAdapter
            return AnthropicAdapter(model=m, api_key=key)
        case "gemini":
            from app.llm.providers.gemini_adapter import GeminiAdapter
            return GeminiAdapter(model=m, api_key=key)
        case "openrouter":
            from app.llm.providers.openrouter_adapter import OpenRouterAdapter
            return OpenRouterAdapter(model=m, api_key=key)
        case "ollama":
            from app.llm.providers.ollama_adapter import OllamaAdapter
            return OllamaAdapter(model=m, base_url=settings.OLLAMA_BASE_URL)
        case _:
            raise ValueError(f"Unknown LLM_PROVIDER: {p!r}")


def get_all_providers() -> list[dict]:
    """
    Return ALL supported providers with their model lists.
    Used by admin tooling and diagnostics.
    """
    all_provider_ids = [
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic Claude"),
        ("gemini", "Google Gemini"),
        ("openrouter", "OpenRouter"),
        ("ollama", "Ollama (local, free)"),
    ]
    result = []
    for pid, label in all_provider_ids:
        models = models_for_provider(pid)
        result.append({
            "id": pid,
            "label": label,
            "model": default_model_for_provider(pid),
            "models": models,
            "requires_key": pid != "ollama",
            "key_url": {
                "openai": "https://platform.openai.com/api-keys",
                "anthropic": "https://console.anthropic.com/",
                "gemini": "https://aistudio.google.com/apikey",
                "openrouter": "https://openrouter.ai/keys",
            }.get(pid, ""),
            "has_env_key": _is_real_api_key(_get_default_key(pid)),
        })
    return result


def get_configured_providers() -> list[dict]:
    """Return providers that have a key configured, for the UI picker."""
    providers = []

    def _add(provider_id: str, label: str) -> None:
        models = models_for_provider(provider_id)
        default = (
            settings.LLM_MODEL
            if settings.LLM_PROVIDER == provider_id
            else default_model_for_provider(provider_id)
        )
        providers.append({
            "id": provider_id,
            "label": label,
            "model": default,
            "models": models,
        })

    if _is_real_api_key(settings.OPENAI_API_KEY):
        _add("openai", "OpenAI")
    if _is_real_api_key(settings.ANTHROPIC_API_KEY):
        _add("anthropic", "Anthropic Claude")
    if _is_real_api_key(settings.GOOGLE_API_KEY):
        _add("gemini", "Google Gemini")
    if _is_real_api_key(settings.OPENROUTER_API_KEY):
        _add("openrouter", "OpenRouter")
    # Ollama is always available (no key required)
    _add("ollama", "Ollama (local)")
    return providers


# FastAPI dependency
async def llm_dependency() -> LLMClient:
    return get_llm_client()
