"""Admin promo code CRUD tests."""

from __future__ import annotations

import uuid

import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminRole
from tests.admin.conftest import issue_admin_session, make_admin


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_admin_promo_codes_list_requires_auth(app_client: AsyncClient) -> None:
    resp = await app_client.get("/api/admin/promo-codes")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_promo_codes_create_and_list(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email="promo-admin@example.com",
        role=AdminRole.super_admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    create_resp = await app_client.post(
        "/api/admin/promo-codes",
        json={
            "code": "launch2026",
            "grant_type": "extra_credits",
            "payload": {"amount": 7, "credit_kind": "free"},
            "max_redemptions": 100,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["promo_code"]["code"] == "LAUNCH2026"
    assert body["promo_code"]["redemption_count"] == 0
    assert body["audit_log_id"]

    list_resp = await app_client.get("/api/admin/promo-codes", headers=headers)
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["grant_type"] == "extra_credits"


@pytest.mark.asyncio
async def test_admin_promo_codes_create_price_discount_offer(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email=f"discount-admin-{uuid.uuid4().hex[:6]}@example.com",
        role=AdminRole.super_admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    expires = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    create_resp = await app_client.post(
        "/api/admin/promo-codes",
        json={
            "code": "upgrade40",
            "grant_type": "price_discount",
            "payload": {
                "stripe_promotion_code_id": "promo_test_upgrade40",
                "applicable_plan_codes": ["monthly_pro", "yearly_pro"],
                "display_name": "Upgrade 40% off",
                "headline": "Limited launch pricing",
            },
            "max_redemptions": 500,
            "expires_at": expires,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    promo = create_resp.json()["promo_code"]
    assert promo["grant_type"] == "price_discount"
    assert promo["offer_summary"] == "Upgrade 40% off"
    assert promo["remaining_redemptions"] == 500
    assert promo["is_redeemable"] is True

    get_resp = await app_client.get(
        f"/api/admin/promo-codes/{promo['id']}",
        headers=headers,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["code"] == "UPGRADE40"

    filtered = await app_client.get(
        "/api/admin/promo-codes",
        params={"grant_type": "price_discount"},
        headers=headers,
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1


@pytest.mark.asyncio
async def test_public_billing_offer_returns_server_deadline(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email=f"public-offer-admin-{uuid.uuid4().hex[:6]}@example.com",
        role=AdminRole.super_admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    expires = datetime.now(timezone.utc) + timedelta(days=3)
    create_resp = await app_client.post(
        "/api/admin/promo-codes",
        json={
            "code": "PUBLICOFFER",
            "grant_type": "price_discount",
            "payload": {
                "stripe_promotion_code_id": "promo_public",
                "display_name": "Public countdown offer",
            },
            "expires_at": expires.isoformat(),
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text

    offer_resp = await app_client.get("/api/billing/offers/PUBLICOFFER")
    assert offer_resp.status_code == 200, offer_resp.text
    body = offer_resp.json()
    assert body["display_name"] == "Public countdown offer"
    assert body["expires_at"] is not None
    assert "stripe_promotion_code_id" not in body


@pytest.mark.asyncio
async def test_admin_promo_codes_update_deactivate(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email="promo-patch@example.com",
        role=AdminRole.admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    create_resp = await app_client.post(
        "/api/admin/promo-codes",
        json={
            "code": "PATCHME",
            "grant_type": "feature_unlock",
            "payload": {"feature": "career_watch"},
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    promo_id = create_resp.json()["promo_code"]["id"]

    patch_resp = await app_client.patch(
        f"/api/admin/promo-codes/{promo_id}",
        json={"is_active": False, "max_redemptions": 50},
        headers=headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    patched = patch_resp.json()["promo_code"]
    assert patched["is_active"] is False
    assert patched["max_redemptions"] == 50
    assert patch_resp.json()["audit_log_id"]


@pytest.mark.asyncio
async def test_admin_promo_codes_create_denied_for_support_agent(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email="support-promo@example.com",
        role=AdminRole.support_agent,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    resp = await app_client.post(
        "/api/admin/promo-codes",
        json={
            "code": "NOPE",
            "grant_type": "extra_credits",
            "payload": {"amount": 1, "credit_kind": "free"},
        },
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_promo_codes_create_rejects_duplicate(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email=f"dup-{uuid.uuid4().hex[:6]}@example.com",
        role=AdminRole.super_admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    payload = {
        "code": "DUPLICATE",
        "grant_type": "extra_credits",
        "payload": {"amount": 2, "credit_kind": "free"},
    }
    first = await app_client.post(
        "/api/admin/promo-codes",
        json=payload,
        headers=headers,
    )
    assert first.status_code == 201

    second = await app_client.post(
        "/api/admin/promo-codes",
        json=payload,
        headers=headers,
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "promo_code_exists"


@pytest.mark.asyncio
async def test_admin_promo_codes_create_with_restricted_user(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email=f"restricted-admin-{uuid.uuid4().hex[:6]}@example.com",
        role=AdminRole.super_admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    from tests.integration.test_auth import REGISTER_PAYLOAD

    register_payload = {**REGISTER_PAYLOAD, "email": "restricted-target@example.com"}
    register_resp = await app_client.post("/api/auth/register", json=register_payload)
    assert register_resp.status_code == 201, register_resp.text
    user_id = register_resp.json()["user"]["id"]

    create_resp = await app_client.post(
        "/api/admin/promo-codes",
        json={
            "code": "USERONLY",
            "grant_type": "extra_credits",
            "payload": {"amount": 4, "credit_kind": "free"},
            "restricted_user_id": user_id,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    promo = create_resp.json()["promo_code"]
    assert promo["restricted_user_id"] == user_id
    assert promo["max_redemptions"] == 1

    list_resp = await app_client.get("/api/admin/promo-codes", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["restricted_user_id"] == user_id


@pytest.mark.asyncio
async def test_admin_promo_codes_create_rejects_unknown_restricted_user(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email=f"unknown-user-admin-{uuid.uuid4().hex[:6]}@example.com",
        role=AdminRole.super_admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    resp = await app_client.post(
        "/api/admin/promo-codes",
        json={
            "code": "ORPHAN",
            "grant_type": "extra_credits",
            "payload": {"amount": 1, "credit_kind": "free"},
            "restricted_user_id": str(uuid.uuid4()),
        },
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "user_not_found"


@pytest.mark.asyncio
async def test_admin_promo_code_redemptions_list(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email=f"redemptions-admin-{uuid.uuid4().hex[:6]}@example.com",
        role=AdminRole.super_admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    from tests.integration.test_auth import REGISTER_PAYLOAD

    register_payload = {**REGISTER_PAYLOAD, "email": "redeemer@example.com"}
    register_resp = await app_client.post("/api/auth/register", json=register_payload)
    assert register_resp.status_code == 201, register_resp.text
    token = register_resp.json()["access_token"]

    create_resp = await app_client.post(
        "/api/admin/promo-codes",
        json={
            "code": "REDEEMLIST",
            "grant_type": "extra_credits",
            "payload": {"amount": 2, "credit_kind": "free"},
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    promo_id = create_resp.json()["promo_code"]["id"]

    redeem_resp = await app_client.post(
        "/api/promo/redeem",
        json={"code": "REDEEMLIST"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert redeem_resp.status_code == 200, redeem_resp.text

    list_resp = await app_client.get(
        f"/api/admin/promo-codes/{promo_id}/redemptions",
        headers=headers,
    )
    assert list_resp.status_code == 200, list_resp.text
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["promo_code_id"] == promo_id


@pytest.mark.asyncio
async def test_admin_user_promo_codes_list(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _ = await make_admin(
        db_session,
        email=f"user-promos-admin-{uuid.uuid4().hex[:6]}@example.com",
        role=AdminRole.super_admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    from tests.integration.test_auth import REGISTER_PAYLOAD

    register_payload = {**REGISTER_PAYLOAD, "email": "coupon-owner@example.com"}
    register_resp = await app_client.post("/api/auth/register", json=register_payload)
    assert register_resp.status_code == 201, register_resp.text
    user_id = register_resp.json()["user"]["id"]

    create_resp = await app_client.post(
        "/api/admin/promo-codes",
        json={
            "code": "OWNERSONLY",
            "grant_type": "extra_credits",
            "payload": {"amount": 6, "credit_kind": "free"},
            "restricted_user_id": user_id,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text

    list_resp = await app_client.get(
        f"/api/admin/users/{user_id}/promo-codes",
        headers=headers,
    )
    assert list_resp.status_code == 200, list_resp.text
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["code"] == "OWNERSONLY"
    assert rows[0]["restricted_user_id"] == user_id
