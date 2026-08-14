"""Career Watch API integration tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


async def _register(client: AsyncClient) -> str:
    payload = {
        **REGISTER_PAYLOAD,
        "email": f"cw-{uuid.uuid4().hex[:8]}@example.com",
    }
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_career_watch_detect_requires_auth(app_client: AsyncClient) -> None:
    resp = await app_client.post(
        "/api/career-watch/detect",
        json={"careers_page_url": "https://boards.greenhouse.io/acme"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_career_watch_create_and_list(app_client: AsyncClient) -> None:
    token = await _register(app_client)
    headers = {"Authorization": f"Bearer {token}"}

    detect_resp = await app_client.post(
        "/api/career-watch/detect",
        json={"careers_page_url": "https://boards.greenhouse.io/acme"},
        headers=headers,
    )
    assert detect_resp.status_code == 200
    assert detect_resp.json()["ats_type"] == "greenhouse"

    create_resp = await app_client.post(
        "/api/career-watch/watches",
        json={
            "careers_page_url": "https://boards.greenhouse.io/acme",
            "company_name": "Acme Corp",
            "keywords": ["python", "backend"],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["company_name"] == "Acme Corp"
    assert body["keywords"] == ["python", "backend"]

    list_resp = await app_client.get("/api/career-watch/watches", headers=headers)
    assert list_resp.status_code == 200
    watches = list_resp.json()
    assert len(watches) == 1
    assert watches[0]["id"] == body["id"]

    limits_resp = await app_client.get("/api/career-watch/limits", headers=headers)
    assert limits_resp.status_code == 200
    limits = limits_resp.json()
    assert limits["active_watches"] == 1
    assert limits["max_companies"] >= 1
