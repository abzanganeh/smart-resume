"""Turnstile verification helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.services.auth.turnstile import (
    assert_turnstile_production_keys,
    verify_turnstile_token,
)

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_verify_turnstile_token_success() -> None:
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {"success": True}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.auth.turnstile.httpx.AsyncClient", return_value=mock_client):
        ok = await verify_turnstile_token(token="abc", remote_ip="127.0.0.1")

    assert ok is True
    mock_client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_turnstile_token_rejects_empty_token() -> None:
    assert await verify_turnstile_token(token="", remote_ip=None) is False


def test_production_refuses_dummy_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "TURNSTILE_SITE_KEY", "1x00000000000000000000AA")
    monkeypatch.setattr(
        settings,
        "TURNSTILE_SECRET_KEY",
        "1x0000000000000000000000000000000AA",
    )
    with pytest.raises(RuntimeError, match="dummy keys"):
        assert_turnstile_production_keys()
