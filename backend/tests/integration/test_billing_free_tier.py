"""Public free-tier starting credits endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminRole
from tests.admin.conftest import issue_admin_session, make_admin


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_billing_free_tier_public_default(app_client: AsyncClient) -> None:
    resp = await app_client.get("/api/billing/free-tier")
    assert resp.status_code == 200, resp.text
    assert resp.json()["starting_credits"] == 3


@pytest.mark.asyncio
async def test_billing_free_tier_reflects_admin_grant(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email="public-free-tier@example.com",
        role=AdminRole.super_admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    patch_resp = await app_client.patch(
        "/api/admin/credits/free-grant",
        json={"amount": 8},
        headers=headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text

    public_resp = await app_client.get("/api/billing/free-tier")
    assert public_resp.status_code == 200
    assert public_resp.json()["starting_credits"] == 8
