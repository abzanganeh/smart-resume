from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load backend/.env regardless of the shell's current working directory.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

_ALLOWED_APP_ENVS = {"local", "development", "ci", "staging", "production"}


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
    USE_IN_MEMORY_STORE: bool = True  # True by default so local dev works without Redis

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

    # Database (PostgreSQL + pgvector)
    # Required for all environments except pure in-memory local dev.
    # Set via DATABASE_URL env var or .env file.
    DATABASE_URL: str = ""

    # App environment — controls security decisions, feature flags, and debug helpers.
    # Allowed values: local | development | ci | staging | production
    # Never compare APP_ENV directly outside this module; use is_production_grade() instead.
    APP_ENV: str = "local"

    # ---------------------------------------------------------------
    # Auth secrets (Release Phase 2 §18.2 / §18.12)
    # ---------------------------------------------------------------
    # 32-byte hex string used to sign JWTs (HS256). MUST be set in any non-local env.
    AUTH_SECRET: str = ""
    # 32-byte hex string used to derive the AES-256-GCM key for BYOK API keys
    # and TOTP secrets. MUST be set in any non-local env.
    BYOK_ENCRYPTION_KEY: str = ""

    # OAuth providers (Google / GitHub)
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    # Transactional email (Resend)
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "noreply@zanganehai.com"

    # Base URL of the frontend, used to build email links (verify/reset/etc.)
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # Token TTLs (seconds) — overridable per environment for testing.
    ACCESS_TOKEN_TTL_SECONDS: int = 15 * 60        # 15 min — §18.2 hard cap
    REFRESH_TOKEN_TTL_SECONDS: int = 7 * 24 * 3600  # 7 days
    EMAIL_VERIFY_TTL_SECONDS: int = 24 * 3600       # 24 h
    PASSWORD_RESET_TTL_SECONDS: int = 3600          # 1 h
    TFA_CHALLENGE_TTL_SECONDS: int = 5 * 60         # 5 min

    # Failed-login lockout window (§18.2 "5 failures in 15 min → lockout").
    LOGIN_FAILURE_WINDOW_SECONDS: int = 15 * 60
    LOGIN_FAILURE_LOCKOUT_THRESHOLD: int = 5

    @field_validator("APP_ENV")
    @classmethod
    def _validate_app_env(cls, v: str) -> str:
        if v not in _ALLOWED_APP_ENVS:
            raise ValueError(
                f"APP_ENV={v!r} is not valid. "
                f"Allowed values: {sorted(_ALLOWED_APP_ENVS)}"
            )
        return v


settings = Settings()


def is_production_grade() -> bool:
    """Return True when running in an environment that requires full security hardening.

    Import and call this function instead of comparing APP_ENV directly.
    Security-sensitive code paths (auth enforcement, debug endpoint gating,
    relaxed CORS, etc.) must gate on this helper, never on raw APP_ENV strings.
    """
    return settings.APP_ENV in {"ci", "staging", "production"}
