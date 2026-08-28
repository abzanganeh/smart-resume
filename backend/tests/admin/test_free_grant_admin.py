"""Admin free starting credits API tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminRole
from tests.admin.conftest import issue_admin_session, make_admin
from tests.integration.test_auth import REGISTER_PAYLOAD


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_admin_free_grant_get_requires_auth(app_client: AsyncClient) -> None:
    resp = await app_client.get("/api/admin/credits/free-grant")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_free_grant_get_default_seed(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email="free-grant-admin@example.com",
        role=AdminRole.super_admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    resp = await app_client.get("/api/admin/credits/free-grant", headers=headers)
    assert resp.status_code == 200, resp.text
    # Registration grant (tier_limits free resumes_per_period).
    assert resp.json()["amount"] == 3


@pytest.mark.asyncio
async def test_admin_free_grant_patch_upserts_and_affects_new_signups(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email="free-grant-patch@example.com",
        role=AdminRole.admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    patch_resp = await app_client.patch(
        "/api/admin/credits/free-grant",
        json={"amount": 5},
        headers=headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    body = patch_resp.json()
    assert body["free_grant"]["amount"] == 5
    assert body["audit_log_id"]

    get_resp = await app_client.get("/api/admin/credits/free-grant", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["amount"] == 5

    register_payload = {**REGISTER_PAYLOAD, "email": "new-grant-user@example.com"}
    register_resp = await app_client.post("/api/auth/register", json=register_payload)
    assert register_resp.status_code == 201, register_resp.text
    assert register_resp.json()["user"]["credit_balance"] == 5


@pytest.mark.asyncio
async def test_admin_free_grant_patch_denied_for_support(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email="support-free-grant@example.com",
        role=AdminRole.support_agent,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    resp = await app_client.patch(
        "/api/admin/credits/free-grant",
        json={"amount": 4},
        headers=headers,
    )
    assert resp.status_code == 403
