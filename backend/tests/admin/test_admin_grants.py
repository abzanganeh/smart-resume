"""Admin user grants API tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminRole
from app.models.user import AuthProvider, User, UserTier
from app.services.billing.credits import get_balance
from app.models.billing import CreditKind
from tests.admin.conftest import issue_admin_session, make_admin


pytestmark = pytest.mark.integration


async def _make_user(db: AsyncSession, email: str = "user@example.com") -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name="Grant User",
        auth_provider=AuthProvider.email,
        password_hash="$2b$12$placeholder.placeholder.placeholder.placeholder.placeholder",
        tier=UserTier.free,
        accepted_tos_version="2026-06",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_admin_grants_create_requires_auth(app_client: AsyncClient) -> None:
    resp = await app_client.post(
        "/api/admin/grants",
        json={
            "user_id": str(uuid.uuid4()),
            "grant_type": "extra_credits",
            "payload": {"amount": 3, "credit_kind": "free"},
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_grants_create_extra_credits_and_list(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    admin, _ = await make_admin(
        db_session,
        email="support@example.com",
        role=AdminRole.support_agent,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    create_resp = await app_client.post(
        "/api/admin/grants",
        json={
            "user_id": str(user.id),
            "grant_type": "extra_credits",
            "payload": {"amount": 5, "credit_kind": "free", "note": "goodwill"},
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["grant"]["grant_type"] == "extra_credits"
    assert body["grant"]["payload"]["amount"] == 5
    assert body["grant"]["revoked_at"] is None
    assert body["audit_log_id"]

    balance = await get_balance(
        db_session, user_id=user.id, credit_kind=CreditKind.free
    )
    assert balance == 5

    list_resp = await app_client.get(
        f"/api/admin/users/{user.id}/grants",
        headers=headers,
    )
    assert list_resp.status_code == 200
    grants = list_resp.json()
    assert len(grants) == 1
    assert grants[0]["id"] == body["grant"]["id"]


@pytest.mark.asyncio
async def test_admin_grants_revoke(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, email="revoke@example.com")
    admin, _ = await make_admin(
        db_session,
        email="super@example.com",
        role=AdminRole.super_admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    create_resp = await app_client.post(
        "/api/admin/grants",
        json={
            "user_id": str(user.id),
            "grant_type": "tier_override",
            "payload": {"plan_code": "monthly_pro"},
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    grant_id = create_resp.json()["grant"]["id"]

    revoke_resp = await app_client.patch(
        f"/api/admin/grants/{grant_id}/revoke",
        headers=headers,
    )
    assert revoke_resp.status_code == 200, revoke_resp.text
    revoked = revoke_resp.json()["grant"]
    assert revoked["revoked_at"] is not None
    assert revoke_resp.json()["audit_log_id"]


@pytest.mark.asyncio
async def test_admin_grants_create_denied_for_read_only(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, email="readonly@example.com")
    admin, _ = await make_admin(
        db_session,
        email="analyst@example.com",
        role=AdminRole.read_only_analyst,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    resp = await app_client.post(
        "/api/admin/grants",
        json={
            "user_id": str(user.id),
            "grant_type": "extra_credits",
            "payload": {"amount": 1, "credit_kind": "free"},
        },
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_grants_feature_unlock_invalid_payload(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, email="feature-invalid@example.com")
    admin, _ = await make_admin(
        db_session,
        email="support3@example.com",
        role=AdminRole.support_agent,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    resp = await app_client.post(
        "/api/admin/grants",
        json={
            "user_id": str(user.id),
            "grant_type": "feature_unlock",
            "payload": {"feature": "not_a_real_feature"},
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_grant_payload"


@pytest.mark.asyncio
async def test_admin_grants_extra_credits_invalid_payload(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, email="invalid@example.com")
    admin, _ = await make_admin(
        db_session,
        email="support2@example.com",
        role=AdminRole.support_agent,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    resp = await app_client.post(
        "/api/admin/grants",
        json={
            "user_id": str(user.id),
            "grant_type": "extra_credits",
            "payload": {"amount": 0, "credit_kind": "free"},
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_grant_payload"
