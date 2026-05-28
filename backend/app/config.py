from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load backend/.env regardless of the shell's current working directory.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM provider — one of: openai | anthropic | gemini | openrouter | ollama
    LLM_PROVIDER: Literal["openai", "anthropic", "gemini", "openrouter", "ollama"] = "openai"
    LLM_MODEL: str = "gpt-4o"

    # Provider API keys (only the key for the active provider is required)
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    USE_IN_MEMORY_STORE: bool = False  # set True in dev to skip Redis

    # Session
    SESSION_TTL_SECONDS: int = 86400  # 24 hours
    SESSION_EXPIRY_WARN_SECONDS: int = 72000  # 20 hours — show banner after this

    # Security
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]
    SENTRY_DSN: str = ""

    # Upload limits
    MAX_RESUME_CHARS: int = 15_000
    MAX_JD_CHARS: int = 10_000
    MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024  # 5 MB


settings = Settings()
