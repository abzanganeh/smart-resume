"""Admin tier limits API tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminRole
from app.services.billing.tier_limits import seed_row_for_plan
from tests.admin.conftest import issue_admin_session, make_admin


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_admin_tier_limits_list_requires_auth(app_client: AsyncClient) -> None:
    resp = await app_client.get("/api/admin/tier-limits")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_tier_limits_create_and_list(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email="super@example.com",
        role=AdminRole.super_admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    seed = seed_row_for_plan("monthly_pro")
    assert seed is not None
    payload = {k: v for k, v in seed.items() if k != "plan_code"}
    payload["plan_code"] = seed["plan_code"]

    create_resp = await app_client.post(
        "/api/admin/tier-limits",
        json=payload,
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["tier_limits"]["plan_code"] == "monthly_pro"
    assert body["audit_log_id"]

    list_resp = await app_client.get("/api/admin/tier-limits", headers=headers)
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["resumes_per_period"] == 50


@pytest.mark.asyncio
async def test_admin_tier_limits_create_denied_for_read_only(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email="analyst@example.com",
        role=AdminRole.read_only_analyst,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    seed = seed_row_for_plan("weekly")
    assert seed is not None
    payload = {k: v for k, v in seed.items() if k != "plan_code"}
    payload["plan_code"] = seed["plan_code"]

    resp = await app_client.post(
        "/api/admin/tier-limits",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 403
