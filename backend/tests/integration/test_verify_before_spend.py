"""Regression: signup credits are visible but unspendable until email verification."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_unverified_user_sees_locked_credits_on_me(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "locked-credits@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    body = reg.json()["user"]
    assert body["credit_balance"] == 6
    assert body["spendable_credit_balance"] == 0
    assert body["credits_locked_until_verification"] is True
    assert body["email_verified_at"] is None


@pytest.mark.asyncio
async def test_verifying_email_unlocks_spendable_credits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "unlock-credits@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    token = reg.json()["access_token"]

    user = (
        await db_session.execute(select(User).where(User.email == payload["email"]))
    ).scalar_one()
    from datetime import datetime, timezone

    user.email_verified_at = datetime.now(timezone.utc)
    await db_session.commit()

    me = await app_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["credit_balance"] == 6
    assert body["spendable_credit_balance"] == 6
    assert body["credits_locked_until_verification"] is False


@pytest.mark.asyncio
async def test_unverified_user_cannot_deduct_flint_credits(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "no-spend@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    token = reg.json()["access_token"]

    resp = await app_client.post(
        "/api/credits/deduct",
        json={
            "action": "digest_extraction",
            "product": "career_flint",
            "session_id": "test-session",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "credits_locked_until_verification"


@pytest.mark.asyncio
async def test_locked_fields_present_on_subscription_and_dashboard(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "fields@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    sub = await app_client.get("/api/subscriptions/current", headers=headers)
    assert sub.status_code == 200, sub.text
    sub_body = sub.json()
    assert sub_body["credit_balance"] == 6
    assert sub_body["spendable_credit_balance"] == 0
    assert sub_body["credits_locked_until_verification"] is True

    dash = await app_client.get("/api/dashboard/summary", headers=headers)
    assert dash.status_code == 200, dash.text
    dash_body = dash.json()
    assert dash_body["credit_balance"] == 6
    assert dash_body["spendable_credit_balance"] == 0
    assert dash_body["credits_locked_until_verification"] is True
