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


def _supply_chain_job_yaml(workflow_text: str) -> str:
    start = workflow_text.index("security-supply-chain:")
    end = workflow_text.index("backend-security:", start)
    return workflow_text[start:end]


def test_supply_chain_job_is_blocking_and_uses_pip_audit_script() -> None:
    workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    job = _supply_chain_job_yaml(workflow.read_text(encoding="utf-8"))
    job_header = job.split("steps:", 1)[0]
    assert "continue-on-error: true" not in job_header
    assert "run-pip-audit.sh" in job

    pip_step = job.split("pip-audit", 1)[1].split("- name:", 1)[0]
    assert "continue-on-error" not in pip_step

    script = REPO_ROOT / "backend" / "ci" / "run-pip-audit.sh"
    allowlist = REPO_ROOT / "backend" / "ci" / "pip-audit-allowlist.txt"
    assert script.is_file()
    assert allowlist.is_file()


def test_pip_audit_allowlist_entries_are_documented() -> None:
    allowlist = REPO_ROOT / "backend" / "ci" / "pip-audit-allowlist.txt"
    security_md = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    raw = allowlist.read_text(encoding="utf-8")

    vuln_ids: list[str] = []
    for line in raw.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped:
            vuln_ids.append(stripped)

    assert vuln_ids, "allowlist must contain at least one PYSEC id"
    for vid in vuln_ids:
        assert vid.startswith("PYSEC-"), f"unexpected allowlist entry: {vid}"
        assert vid in security_md or vid in raw, f"{vid} must be documented in SECURITY.md or allowlist comments"
