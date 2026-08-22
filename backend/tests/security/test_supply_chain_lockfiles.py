"""Supply-chain invariants for OWASP A03 / LLM04 (M23 A1)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_backend_uv_lockfile_exists_and_is_non_empty() -> None:
    lockfile = REPO_ROOT / "backend" / "uv.lock"
    assert lockfile.is_file(), "backend/uv.lock must be committed for reproducible installs"
    assert lockfile.stat().st_size > 100, "backend/uv.lock looks truncated or empty"


def test_frontend_pnpm_lockfile_exists_and_is_non_empty() -> None:
    lockfile = REPO_ROOT / "frontend" / "pnpm-lock.yaml"
    assert lockfile.is_file(), "frontend/pnpm-lock.yaml must be committed for reproducible installs"
    assert lockfile.stat().st_size > 100, "frontend/pnpm-lock.yaml looks truncated or empty"


def test_dependabot_configures_grouped_weekly_updates() -> None:
    config = REPO_ROOT / ".github" / "dependabot.yml"
    text = config.read_text(encoding="utf-8")
    assert "package-ecosystem: uv" in text
    assert "package-ecosystem: npm" in text
    assert "interval: weekly" in text
    assert "groups:" in text


def test_ci_declares_supply_chain_and_security_test_jobs() -> None:
    workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "security-supply-chain:" in text
    assert "backend-security:" in text
    assert "pip-audit" in text
    assert "pnpm audit" in text
    assert "gitleaks" in text
