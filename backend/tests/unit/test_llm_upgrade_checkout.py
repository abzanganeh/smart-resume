"""LLM upgrade checkout is removed — quality is included in subscription tier."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_llm_upgrade_checkout_returns_gone(app_client: AsyncClient) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "llm-gone@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]

    resp = await app_client.post(
        "/api/subscriptions/llm-upgrade/checkout",
        json={
            "code": "better_5pack",
            "success_url": "http://localhost:3000/success",
            "cancel_url": "http://localhost:3000/cancel",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 410, resp.text
    assert resp.json()["detail"]["code"] == "llm_upgrade_removed"
