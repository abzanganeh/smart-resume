"""Registration Turnstile enforcement."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_register_requires_turnstile_token(app_client: AsyncClient) -> None:
    payload = {k: v for k, v in REGISTER_PAYLOAD.items() if k != "turnstile_token"}
    resp = await app_client.post("/api/auth/register", json=payload)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_register_rejects_failed_turnstile(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fail(*, token: str, remote_ip: str | None = None) -> bool:
        return False

    monkeypatch.setattr("app.routers.auth.verify_turnstile_token", _fail)
    payload = {**REGISTER_PAYLOAD, "email": "turnstile-fail@example.com"}
    resp = await app_client.post("/api/auth/register", json=payload)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["code"] == "turnstile_failed"


@pytest.mark.asyncio
async def test_register_config_exposes_site_key(app_client: AsyncClient) -> None:
    resp = await app_client.get("/api/auth/register-config")
    assert resp.status_code == 200, resp.text
    assert resp.json()["turnstile_site_key"]
