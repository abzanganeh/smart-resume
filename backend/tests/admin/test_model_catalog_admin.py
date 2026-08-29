"""Admin model catalog API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.model_catalog import MODEL_CATALOG
from app.models.admin import AdminRole
from tests.admin.conftest import issue_admin_session, make_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_model_catalog_requires_auth(app_client: AsyncClient) -> None:
    resp = await app_client.get("/api/admin/llm/model-catalog")
    assert resp.status_code == 401


async def test_model_catalog_returns_catalog(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _secret = await make_admin(
        db_session, email="catalog@example.com", role=AdminRole.super_admin
    )
    await db_session.commit()
    token, headers = await issue_admin_session(admin.id)

    resp = await app_client.get(
        "/api/admin/llm/model-catalog",
        headers={**headers, "Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["providers"].keys()) == set(MODEL_CATALOG.keys())
    for provider, entries in body["providers"].items():
        assert entries, f"{provider} should have at least one model"
        for entry in entries:
            assert "id" in entry and entry["id"]
            assert "label" in entry and entry["label"]
    assert body["providers"]["gemini"][0]["id"] == MODEL_CATALOG["gemini"][0]["id"]
