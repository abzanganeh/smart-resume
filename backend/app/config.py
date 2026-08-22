from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
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

    # Platform-owned key for master-resume embeddings (IMPLEMENTATION_PLAN §6a).
    # This is *not* the user's BYOK key — embeddings always use the
    # canonical retrieval model (text-embedding-3-small) so JD↔chunk
    # vectors live in the same space regardless of which chat model the
    # user has selected.  In local/dev it falls back to OPENAI_API_KEY
    # so a single key suffices.
    OPENAI_EMBEDDING_KEY: str = ""

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    USE_IN_MEMORY_STORE: bool = True  # True by default so local dev works without Redis

    # Session
    SESSION_TTL_SECONDS: int = 86400  # 24 hours
    SESSION_EXPIRY_WARN_SECONDS: int = 72000  # 20 hours — show banner after this

    # Flint cross-product handoff (Strategy B Phase 1)
    FLINT_HANDOFF_TTL_SECONDS: int = 600

    # Company intelligence cache TTL in days.  Profiles older than this are
    # re-extracted on the next Phase 1 completion for that company.
    COMPANY_INTEL_CACHE_DAYS: int = 30

    # Strategy B Phase 2 — Extension auth
    # Default is True so local development and CI exercise the route
    # without an extra env var. Production deployments should explicitly
    # set EXTENSION_AUTH_ENABLED=False until the extension is published —
    # disabling returns 403 with code "extension_auth_disabled" from both
    # /api/auth/extension/login and /refresh, fail-closed without leaking
    # endpoint existence (404 would imply the route never existed).
    EXTENSION_AUTH_ENABLED: bool = True
    JD_TEXT_MAX_CHARS: int = 20_000

    # Security
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]
    SENTRY_DSN: str = ""

    # Upload limits
    MIN_RESUME_CHARS: int = 200
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
    AZURE_AD_CLIENT_ID: str = ""
    AZURE_AD_CLIENT_SECRET: str = ""
    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""

    # Transactional email (Resend in staging/production; Mailpit SMTP locally)
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "noreply@zanganehai.com"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 1025

    # Web push (VAPID) — §19.5 / IMPLEMENTATION_PLAN §6b
    WEB_PUSH_VAPID_PUBLIC_KEY: str = ""
    WEB_PUSH_VAPID_PRIVATE_KEY: str = ""
    WEB_PUSH_VAPID_SUBJECT: str = "mailto:notifications@zanganehai.com"

    # SMS (Twilio) — interview reminders only
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

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

    # ---------------------------------------------------------------
    # Stripe / Billing (Release Phase 2 §18.3 + IMPLEMENTATION_PLAN §7)
    # ---------------------------------------------------------------
    # Secret API key (sk_live_… / sk_test_…). MUST be set in any non-local env.
    STRIPE_SECRET_KEY: str = ""
    # Webhook signing secret used by stripe.Webhook.construct_event.
    STRIPE_WEBHOOK_SECRET: str = ""

    # Bootstrap / disaster-recovery price IDs for canonical PlanConfig codes.
    # PlanConfig DB rows take precedence at runtime; env vars are fallback only.
    STRIPE_PRICE_WEEKLY: str = ""
    STRIPE_PRICE_MONTHLY_PRO: str = ""
    STRIPE_PRICE_YEARLY_PRO: str = ""
    STRIPE_PRICE_MONTHLY_PLUS: str = ""
    STRIPE_PRICE_YEARLY_PLUS: str = ""
    STRIPE_PRICE_MONTHLY_PREMIUM: str = ""
    STRIPE_PRICE_YEARLY_PREMIUM: str = ""

    STRIPE_PRICE_BETTER_PACK: str = ""        # better_5pack (legacy add-on)
    STRIPE_PRICE_BETTER_MONTHLY: str = ""
    STRIPE_PRICE_BETTER_YEARLY: str = ""

    STRIPE_PRICE_BEST_PER_RESUME: str = ""
    STRIPE_PRICE_BEST_MONTHLY: str = ""
    STRIPE_PRICE_BEST_YEARLY: str = ""

    # Default currency code surfaced by /api/billing/prices (Step 7).
    BILLING_CURRENCY: str = "USD"
    # When true, phase runs and other quota-gated actions skip credit checks.
    # In ``local`` / ``development`` this defaults to enabled unless explicitly false.
    BILLING_SKIP_QUOTA: bool | None = None

    # Hard server-side limits enforced before calling Stripe (§7.7).
    SUBSCRIPTION_PAUSE_MIN_DAYS: int = 7
    SUBSCRIPTION_PAUSE_MAX_DAYS: int = 90
    SUBSCRIPTION_GRACE_HOURS: int = 72
    STRIPE_WEBHOOK_MAX_ATTEMPTS: int = 5

    # ---------------------------------------------------------------
    # Job search (Release Phase 3 §18.10)
    # ---------------------------------------------------------------
    HIREBASE_API_KEY: str = ""
    APIFY_API_TOKEN: str = ""
    APIFY_ACTOR_ID: str = "automation-lab/google-jobs-scraper"
    JOB_CACHE_TTL_COMMON_SECONDS: int = 3600
    JOB_CACHE_TTL_UNIQUE_SECONDS: int = 86400
    JOB_CACHE_SQS_URL: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET_ATTACHMENTS: str = ""
    S3_EXPORT_BUCKET: str = ""
    INTERNAL_SCHEDULER_SECRET: str = ""
    ACCOUNT_CLOSURE_GRACE_DAYS: int = 30

    # Global job corpus poll tiers (minutes)
    GLOBAL_POLL_INTERVAL_TIER_1_MINUTES: int = 15
    GLOBAL_POLL_INTERVAL_TIER_2_MINUTES: int = 30
    GLOBAL_POLL_INTERVAL_TIER_3_MINUTES: int = 45
    JOB_SEARCH_DB_FIRST: bool = True
    JOB_SEARCH_DB_MIN_RESULTS: int = 5

    # ---------------------------------------------------------------
    # Admin panel (Step 35 - IMPLEMENTATION_PLAN section 8.4)
    # ---------------------------------------------------------------
    # Bootstrap super-admin (section 8.4.3).  Empty BOOTSTRAP_SUPER_ADMIN_EMAIL
    # disables the bootstrap hook entirely.  In staging/production an
    # empty BOOTSTRAP_SUPER_ADMIN_PASSWORD aborts bootstrap with an audit
    # entry; in local/development/ci a random password is generated and
    # printed once to stdout.
    BOOTSTRAP_SUPER_ADMIN_EMAIL: str = ""
    BOOTSTRAP_SUPER_ADMIN_PASSWORD: str = ""
    BOOTSTRAP_SUPER_ADMIN_DISPLAY_NAME: str = "Bootstrap Super Admin"

    # Section 8.4.2 - Admin session TTLs.  Absolute 60 minutes,
    # idle 15 minutes.  Admin sessions are NOT sliding.
    ADMIN_SESSION_TTL_SECONDS: int = 60 * 60
    ADMIN_SESSION_IDLE_TTL_SECONDS: int = 15 * 60
    # admin_2fa_setup token TTL - first login before TOTP is enrolled.
    ADMIN_2FA_SETUP_TTL_SECONDS: int = 15 * 60
    # admin_challenge token TTL - issued on credentials login when 2FA
    # is already enrolled, expects /api/admin/auth/2fa/verify next.
    ADMIN_CHALLENGE_TTL_SECONDS: int = 15 * 60
    # Invite acceptance token TTL - invited admin sets password + 2FA.
    ADMIN_INVITE_TTL_SECONDS: int = 7 * 24 * 3600

    # Cloudflare Turnstile (registration CAPTCHA). Dummy keys are injected in
    # non-production when unset — see _apply_environment_defaults.
    TURNSTILE_SITE_KEY: str = ""
    TURNSTILE_SECRET_KEY: str = ""

    # Signup abuse controls (M20 §11j slice 6).
    TRUSTED_PROXY_IPS: list[str] = ["127.0.0.1", "::1"]
    SIGNUP_IP_DAILY_LIMIT: int = 15
    SIGNUP_IP_DEVICE_DAILY_LIMIT: int = 3
    SIGNUP_FINGERPRINT_COLLISION_THRESHOLD: int = 5

    # Unverified email-account cleanup (M20 §11j slice 7).
    UNVERIFIED_ACCOUNT_CLEANUP_DAYS: int = 7
    UNVERIFIED_ACCOUNT_CLEANUP_DRY_RUN: bool = True

    @field_validator("APP_ENV")
    @classmethod
    def _validate_app_env(cls, v: str) -> str:
        if v not in _ALLOWED_APP_ENVS:
            raise ValueError(
                f"APP_ENV={v!r} is not valid. "
                f"Allowed values: {sorted(_ALLOWED_APP_ENVS)}"
            )
        return v

    @model_validator(mode="after")
    def _apply_environment_defaults(self) -> "Settings":
        # Local/dev: 24-hour access tokens (production keeps 15-minute cap).
        if (
            self.APP_ENV in {"local", "development"}
            and self.ACCESS_TOKEN_TTL_SECONDS == 15 * 60
        ):
            object.__setattr__(self, "ACCESS_TOKEN_TTL_SECONDS", 24 * 3600)
        if self.APP_ENV != "production":
            if not self.TURNSTILE_SITE_KEY:
                object.__setattr__(
                    self,
                    "TURNSTILE_SITE_KEY",
                    "1x00000000000000000000AA",
                )
            if not self.TURNSTILE_SECRET_KEY:
                object.__setattr__(
                    self,
                    "TURNSTILE_SECRET_KEY",
                    "1x0000000000000000000000000000000AA",
                )
        return self

    # Phase 3 — LLM rewrite can take 30–120 s on large resumes; cap it so
    # the UI gets a clear timeout instead of hanging indefinitely.
    PHASE3_LLM_TIMEOUT_SECONDS: int = 240
    # Redis phase-lock TTL must exceed the LLM timeout so a second run cannot
    # start while the first is still in flight.
    PHASE_LOCK_TTL_SECONDS: int = 600
    # SSE keepalive interval while the event queue is idle (during LLM calls).
    SSE_KEEPALIVE_SECONDS: int = 15


settings = Settings()


def is_production_grade() -> bool:
    """Return True when running in an environment that requires full security hardening.

    Import and call this function instead of comparing APP_ENV directly.
    Security-sensitive code paths (auth enforcement, debug endpoint gating,
    relaxed CORS, etc.) must gate on this helper, never on raw APP_ENV strings.
    """
    return settings.APP_ENV in {"ci", "staging", "production"}


def should_skip_billing_quota() -> bool:
    """Return True when quota checks should be bypassed (local dev by default)."""
    if settings.BILLING_SKIP_QUOTA is True:
        return True
    if settings.BILLING_SKIP_QUOTA is False:
        return False
    return settings.APP_ENV in {"local", "development"}
