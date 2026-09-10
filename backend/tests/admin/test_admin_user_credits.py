"""Admin user credits PATCH ledger tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminRole
from app.models.billing import CreditKind
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.credits import get_balance, grant_credit
from tests.admin.conftest import issue_admin_session, make_admin


pytestmark = pytest.mark.integration


async def _make_user(db: AsyncSession, email: str = "credits@example.com") -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name="Credits User",
        auth_provider=AuthProvider.email,
        password_hash="$2b$12$placeholder.placeholder.placeholder.placeholder.placeholder",
        tier=UserTier.free,
        accepted_tos_version="2026-06",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_admin_credits_grant_returns_new_balance(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    admin, _ = await make_admin(
        db_session,
        email="support-credits@example.com",
        role=AdminRole.support_agent,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    resp = await app_client.patch(
        f"/api/admin/users/{user.id}/credits",
        json={"delta": 7, "credit_kind": "free", "reason": "staging test grant"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["new_balance"] == 7

    balance = await get_balance(
        db_session, user_id=user.id, credit_kind=CreditKind.free
    )
    assert balance == 7


@pytest.mark.asyncio
async def test_admin_credits_revoke_below_zero_rejected(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, email="revoke-below@example.com")
    await grant_credit(
        db_session,
        user_id=user.id,
        credit_kind=CreditKind.free,
        delta=3,
        reason="seed",
    )
    admin, _ = await make_admin(
        db_session,
        email="support-revoke@example.com",
        role=AdminRole.support_agent,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    resp = await app_client.patch(
        f"/api/admin/users/{user.id}/credits",
        json={"delta": -10, "credit_kind": "free", "reason": "too much"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "revoke_exceeds_balance"


@pytest.mark.asyncio
async def test_admin_user_list_shows_ledger_balance(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, email="list-balance@example.com")
    await grant_credit(
        db_session,
        user_id=user.id,
        credit_kind=CreditKind.free,
        delta=4,
        reason="seed",
    )
    admin, _ = await make_admin(
        db_session,
        email="analyst-list@example.com",
        role=AdminRole.read_only_analyst,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    resp = await app_client.get(
        "/api/admin/users",
        params={"q": user.email},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    match = next((row for row in items if row["id"] == str(user.id)), None)
    assert match is not None
    assert match["credit_balance"] == 4
    assert "subscription_status" in match
