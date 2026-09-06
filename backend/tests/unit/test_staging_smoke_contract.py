"""Contract tests tying staging-smoke.sh assertions to seed tier data.

These values are checked by ``scripts/staging-smoke.sh`` after deploy.
If you change free registration grants or tracker caps, update both places.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.billing.tier_limits import seed_row_for_plan

pytestmark = pytest.mark.unit

# Seed values checked by staging-smoke.sh (B4+). Register credits in smoke
# compare against GET /api/billing/free-tier starting_credits, not a literal here.
EXPECTED_FREE_STARTING_CREDITS = 3
EXPECTED_FREE_TRACKER_ACTIVE_LIMIT = 10


def test_staging_smoke_free_tier_starting_credits() -> None:
    row = seed_row_for_plan("free")
    assert row is not None
    assert row["resumes_per_period"] == EXPECTED_FREE_STARTING_CREDITS
    assert row["cover_letters_per_period"] == EXPECTED_FREE_STARTING_CREDITS


def test_staging_smoke_free_tier_tracker_active_limit() -> None:
    row = seed_row_for_plan("free")
    assert row is not None
    assert row["tracker_active_limit"] == EXPECTED_FREE_TRACKER_ACTIVE_LIMIT


def test_staging_smoke_script_includes_verify_unlock_flow() -> None:
    """CI does not run staging-smoke.sh — grep guards the verify gate contract."""
    script = (
        Path(__file__).resolve().parents[3] / "scripts" / "staging-smoke.sh"
    )
    text = script.read_text()
    required = (
        'check "Backend /health returns 200"',
        "REQUIRE_MAILPIT",
        "/api/v1/search",
        'check "GET /api/auth/verify/{token} returns 200"',
        'check "Register spendable_credit_balance is 0 until verify"',
        'check "Post-verify spendable_credit_balance equals starting credits',
        'check "Post-verify email_verified_at is set"',
        'check "POST /api/jobs/search returns 200 after titles confirmed"',
        "upgrade-insecure-requests",
    )
    for needle in required:
        assert needle in text, f"staging-smoke.sh must contain {needle!r}"


def test_staging_smoke_localhost_defaults_require_mailpit() -> None:
    script = (
        Path(__file__).resolve().parents[3] / "scripts" / "staging-smoke.sh"
    )
    text = script.read_text()
    assert 'REQUIRE_MAILPIT=1' in text
    assert "localhost" in text and "127.0.0.1" in text


def test_production_smoke_sets_require_mailpit_zero() -> None:
    script = (
        Path(__file__).resolve().parents[3] / "scripts" / "production-smoke.sh"
    )
    text = script.read_text()
    assert "CONFIRM_PRODUCTION_SMOKE=1" in text
    assert "REQUIRE_MAILPIT=0" in text
    assert "staging-smoke.sh" in text


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_desktop_staging_local_sim_up_script_contract() -> None:
    """Grep guards the local-sim helper compose triple and port pins."""
    script = _repo_root() / "scripts" / "desktop-staging-local-sim-up.sh"
    text = script.read_text()
    required = (
        "set -euo pipefail",
        "docker-compose.yml",
        "docker-compose.staging.yml",
        "docker-compose.local-sim.yml",
        'STAGING_FRONTEND_PORT="$FRONTEND_PORT"',
        'STAGING_BACKEND_PORT="$BACKEND_PORT"',
        "FRONTEND_PORT=3001",
        "BACKEND_PORT=8001",
        "127.0.0.1:38025",
        "setup-staging-env.py --local-sim",
        "setup-staging-env.py --check",
        "staging-smoke.sh",
        "LOCAL_SIM_ENV_CHECK=1 ./scripts/production-preflight.sh",
        "API_URL=http://localhost:${BACKEND_PORT}",
        "FRONTEND_URL=http://localhost:${FRONTEND_PORT}",
        "--env-file .env.staging",
        "seed_staging_job_cache.py",
        "Missing backend/.env.staging",
        "Missing .env.staging",
    )
    for needle in required:
        assert needle in text, f"desktop-staging-local-sim-up.sh must contain {needle!r}"
    forbidden = (
        "3000:3000",
        "production-smoke",
        "PRODUCTION_ENV_CHECK",
        "stripe listen",
        "ss -tlnp",
        "Stop that listener",
    )
    for needle in forbidden:
        assert needle not in text, f"desktop-staging-local-sim-up.sh must not contain {needle!r}"


def test_setup_staging_env_local_sim_prints_three_file_compose() -> None:
    """Source grep: --local-sim branch must print three-file compose with pinned ports."""
    script = _repo_root() / "scripts" / "setup-staging-env.py"
    text = script.read_text()
    assert "if args.local_sim:" in text
    assert "docker-compose.local-sim.yml" in text
    assert "STAGING_FRONTEND_PORT=3001" in text
    assert "STAGING_BACKEND_PORT=8001" in text
    assert 'sk_test_local_staging_sim' in text


def test_setup_staging_env_non_local_sim_omits_local_sim_compose() -> None:
    """Non-local-sim path must not require docker-compose.local-sim.yml in the else branch."""
    script = _repo_root() / "scripts" / "setup-staging-env.py"
    text = script.read_text()
    else_idx = text.index('    else:\n        print("  docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --build")')
    local_sim_idx = text.index("if args.local_sim:")
    assert local_sim_idx < else_idx
    else_block = text[else_idx : else_idx + 120]
    assert "local-sim" not in else_block


def test_production_preflight_rejects_sk_test_on_https_prod() -> None:
    script = _repo_root() / "scripts" / "production-preflight.sh"
    text = script.read_text()
    required = (
        "STRIPE_SECRET_KEY",
        'stripe.startswith("sk_test_")',
        "must not be sk_test_* on production HTTPS deploy",
        "STRIPE_SECRET_KEY must not be set in .env.staging (backend/.env.staging only)",
        "STRIPE_SECRET_KEY unset on production HTTPS deploy",
        "LOCAL_SIM_ENV_CHECK",
        'stripe.startswith("sk_live_")',
        "must not be sk_live_* in local-sim",
    )
    for needle in required:
        assert needle in text, f"production-preflight.sh must contain {needle!r}"


def test_docker_compose_loopback_binds_sensitive_services() -> None:
    compose = (_repo_root() / "docker-compose.yml").read_text()
    for service in ("postgres", "redis", "mailpit"):
        assert f"  {service}:" in compose
    assert '127.0.0.1:${POSTGRES_HOST_PORT:-54325}:5432' in compose
    assert '127.0.0.1:${REDIS_HOST_PORT:-6380}:6379' in compose
    assert '127.0.0.1:${MAILPIT_SMTP_PORT:-31025}:1025' in compose
    assert '127.0.0.1:${MAILPIT_UI_PORT:-38025}:8025' in compose
