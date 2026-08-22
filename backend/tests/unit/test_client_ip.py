"""Trusted client IP resolution tests."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.services.auth.client_ip import resolve_client_ip

pytestmark = pytest.mark.unit


def _request(*, peer: str, xff: str | None = None) -> Mock:
    request = Mock()
    request.client = Mock(host=peer)
    request.headers = {"x-forwarded-for": xff} if xff else {}
    return request


def test_direct_connection_ignores_xff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.auth.client_ip.settings.TRUSTED_PROXY_IPS",
        ["127.0.0.1"],
    )
    ip = resolve_client_ip(_request(peer="203.0.113.10", xff="198.51.100.20"))
    assert ip == "203.0.113.10"


def test_trusted_proxy_reads_first_untrusted_xff_hop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.auth.client_ip.settings.TRUSTED_PROXY_IPS",
        ["127.0.0.1"],
    )
    ip = resolve_client_ip(
        _request(peer="127.0.0.1", xff="198.51.100.20, 127.0.0.1")
    )
    assert ip == "198.51.100.20"
