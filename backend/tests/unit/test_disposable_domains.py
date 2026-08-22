"""Tests for vendored disposable-email domain blocking."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.auth.disposable_domains import (
    is_disposable_email,
    load_disposable_domains,
)

pytestmark = pytest.mark.unit


def test_known_disposable_domain_is_blocked() -> None:
    assert is_disposable_email("user@mailinator.com") is True


def test_common_provider_is_not_blocked() -> None:
    assert is_disposable_email("user@gmail.com") is False


def test_malformed_email_is_not_treated_as_disposable() -> None:
    assert is_disposable_email("not-an-email") is False


def test_custom_blocklist_file(tmp_path: Path) -> None:
    blocklist = tmp_path / "domains.txt"
    blocklist.write_text("temp.example\n# comment\n\n", encoding="utf-8")
    domains = load_disposable_domains(path=blocklist)
    assert "temp.example" in domains
    assert "gmail.com" not in domains


def test_subdomain_of_listed_disposable_domain_is_blocked() -> None:
    assert is_disposable_email("user@sub.mailinator.com") is True


def test_vendored_blocklist_loads() -> None:
    domains = load_disposable_domains()
    assert "mailinator.com" in domains
    assert len(domains) > 1000
