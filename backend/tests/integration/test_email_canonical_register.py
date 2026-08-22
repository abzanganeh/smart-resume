"""Integration tests for email alias canonicalization on register."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_gmail_alias_collides_with_primary_mailbox(app_client: AsyncClient) -> None:
    first = {**REGISTER_PAYLOAD, "email": "alias-owner@gmail.com"}
    assert (await app_client.post("/api/auth/register", json=first)).status_code == 201

    second = {
        **REGISTER_PAYLOAD,
        "email": "alias.owner+tag@gmail.com",
        "password": "tr0ub4dor&3sandwich-eats-paint2",
    }
    resp = await app_client.post("/api/auth/register", json=second)
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "email_already_registered"
    assert "sign in or reset your password" in detail["message"].lower()


@pytest.mark.asyncio
async def test_corporate_plus_address_is_not_normalized(app_client: AsyncClient) -> None:
    first = {**REGISTER_PAYLOAD, "email": "user@idme24.com"}
    assert (await app_client.post("/api/auth/register", json=first)).status_code == 201

    second = {
        **REGISTER_PAYLOAD,
        "email": "user+alias@idme24.com",
        "password": "tr0ub4dor&3sandwich-eats-paint2",
    }
    assert (await app_client.post("/api/auth/register", json=second)).status_code == 201
