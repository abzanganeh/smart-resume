"""Register rejects disposable email domains."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_register_rejects_disposable_domain(app_client: AsyncClient) -> None:
    payload = {
        **REGISTER_PAYLOAD,
        "email": "farmer@mailinator.com",
    }
    resp = await app_client.post("/api/auth/register", json=payload)
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "disposable_email_not_allowed"
    assert "disposable" in detail["message"].lower()


@pytest.mark.asyncio
async def test_register_allows_regular_domain(app_client: AsyncClient) -> None:
    payload = {
        **REGISTER_PAYLOAD,
        "email": "regular-user@example.com",
    }
    resp = await app_client.post("/api/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
