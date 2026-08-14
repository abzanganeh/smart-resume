"""Unit tests for promo code normalization and timing-safe compare."""

from __future__ import annotations

import pytest

from app.services.billing.promo import (
    codes_match,
    normalize_promo_code,
)


def test_normalize_promo_code_uppercases_and_trims() -> None:
    assert normalize_promo_code("  save10  ") == "SAVE10"


def test_normalize_promo_code_empty_after_trim() -> None:
    assert normalize_promo_code("   ") == ""


def test_codes_match_equal() -> None:
    assert codes_match("SAVE10", "SAVE10") is True


def test_codes_match_rejects_mismatch() -> None:
    assert codes_match("SAVE10", "SAVE11") is False


def test_codes_match_rejects_different_lengths() -> None:
    assert codes_match("SAVE10", "SAVE1") is False


# ---------------------------------------------------------------------------
# Redeem endpoint (integration — requires Postgres)
# ---------------------------------------------------------------------------

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminRole
from app.models.admin_grant import AdminGrantType
from app.models.billing import CreditKind
from app.models.promo_code import PromoCode
from app.services.billing.credits import get_balance
from tests.admin.conftest import issue_admin_session, make_admin
from tests.integration.test_auth import REGISTER_PAYLOAD

_redeem_mark = pytest.mark.integration


async def _register(client: AsyncClient, email: str) -> tuple[str, str]:
    payload = {**REGISTER_PAYLOAD, "email": email}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["access_token"], r.json()["user"]["id"]


async def _create_promo(
    client: AsyncClient,
    db: AsyncSession,
    *,
    code: str = "WELCOME10",
    amount: int = 10,
    max_redemptions: int | None = None,
    expires_at: datetime | None = None,
    is_active: bool = True,
) -> PromoCode:
    admin, _ = await make_admin(
        db,
        email=f"promo-admin-{uuid.uuid4().hex[:6]}@example.com",
        role=AdminRole.super_admin,
    )
    await db.commit()
    _, headers = await issue_admin_session(admin.id)

    create_resp = await client.post(
        "/api/admin/promo-codes",
        json={
            "code": code,
            "grant_type": "extra_credits",
            "payload": {"amount": amount, "credit_kind": "free"},
            "max_redemptions": max_redemptions,
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    promo_id = uuid.UUID(create_resp.json()["promo_code"]["id"])
    row = await db.get(PromoCode, promo_id)
    assert row is not None
    if not is_active:
        row.is_active = False
        await db.flush()
    return row


@_redeem_mark
@pytest.mark.asyncio
async def test_promo_redeem_requires_auth(app_client: AsyncClient) -> None:
    resp = await app_client.post("/api/promo/redeem", json={"code": "NOPE"})
    assert resp.status_code == 401


@_redeem_mark
@pytest.mark.asyncio
async def test_promo_redeem_grants_credits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_promo(app_client, db_session, code="CREDITS5", amount=5)
    token, user_id = await _register(app_client, "promo-user@example.com")

    balance_before = await get_balance(
        db_session,
        user_id=uuid.UUID(user_id),
        credit_kind=CreditKind.free,
    )

    resp = await app_client.post(
        "/api/promo/redeem",
        json={"code": "credits5"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["idempotent"] is False
    assert body["grant_type"] == AdminGrantType.extra_credits.value
    assert body["credit_transaction_id"]

    balance = await get_balance(
        db_session,
        user_id=uuid.UUID(user_id),
        credit_kind=CreditKind.free,
    )
    assert balance == balance_before + 5


@_redeem_mark
@pytest.mark.asyncio
async def test_promo_redeem_is_idempotent_per_user(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_promo(app_client, db_session, code="ONCE", amount=3)
    token, user_id = await _register(app_client, "promo-idem@example.com")

    balance_before = await get_balance(
        db_session,
        user_id=uuid.UUID(user_id),
        credit_kind=CreditKind.free,
    )

    first = await app_client.post(
        "/api/promo/redeem",
        json={"code": "ONCE"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200
    first_body = first.json()

    second = await app_client.post(
        "/api/promo/redeem",
        json={"code": "ONCE"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["idempotent"] is True
    assert second_body["redemption_id"] == first_body["redemption_id"]

    balance = await get_balance(
        db_session,
        user_id=uuid.UUID(user_id),
        credit_kind=CreditKind.free,
    )
    assert balance == balance_before + 3


@_redeem_mark
@pytest.mark.asyncio
async def test_promo_redeem_invalid_code(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_promo(app_client, db_session, code="REAL")
    token, _ = await _register(app_client, "promo-invalid@example.com")

    resp = await app_client.post(
        "/api/promo/redeem",
        json={"code": "FAKE"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "promo_code_invalid"


@_redeem_mark
@pytest.mark.asyncio
async def test_promo_redeem_expired_code(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    await _create_promo(
        app_client,
        db_session,
        code="OLD",
        expires_at=expired,
    )
    token, _ = await _register(app_client, "promo-expired@example.com")

    resp = await app_client.post(
        "/api/promo/redeem",
        json={"code": "OLD"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 410
    assert resp.json()["detail"]["code"] == "promo_code_expired"


@_redeem_mark
@pytest.mark.asyncio
async def test_promo_redeem_exhausted_code(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_promo(
        app_client,
        db_session,
        code="LIMIT1",
        max_redemptions=1,
    )
    token_a, _ = await _register(app_client, "promo-a@example.com")
    token_b, _ = await _register(app_client, "promo-b@example.com")

    ok = await app_client.post(
        "/api/promo/redeem",
        json={"code": "LIMIT1"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert ok.status_code == 200

    exhausted = await app_client.post(
        "/api/promo/redeem",
        json={"code": "LIMIT1"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert exhausted.status_code == 409
    assert exhausted.json()["detail"]["code"] == "promo_code_exhausted"
