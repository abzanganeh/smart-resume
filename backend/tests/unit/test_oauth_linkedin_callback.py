"""LinkedIn OAuth helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.auth.oauth import verify_linkedin_id_token


@pytest.mark.asyncio
async def test_verify_linkedin_id_token_parses_claims() -> None:
    claims = {
        "email": "Linked@Example.com",
        "sub": "abc123",
        "name": "Linked User",
    }

    class FakeResp:
        status_code = 200

        def json(self):
            return {"keys": []}

    with patch("app.services.auth.oauth.settings.LINKEDIN_CLIENT_ID", "client-id"), patch(
        "jose.jwt.decode",
        return_value=claims,
    ), patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        return_value=FakeResp(),
    ):
        profile = await verify_linkedin_id_token("fake.jwt")

    assert profile["email"] == "linked@example.com"
    assert profile["provider_id"] == "abc123"
    assert profile["display_name"] == "Linked User"
    assert profile["email_verified"] is False


@pytest.mark.asyncio
async def test_verify_linkedin_id_token_honours_email_verified_claim() -> None:
    claims = {
        "email": "verified@example.com",
        "sub": "abc123",
        "name": "Verified User",
        "email_verified": True,
    }

    class FakeResp:
        status_code = 200

        def json(self):
            return {"keys": []}

    with patch("app.services.auth.oauth.settings.LINKEDIN_CLIENT_ID", "client-id"), patch(
        "jose.jwt.decode",
        return_value=claims,
    ), patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        return_value=FakeResp(),
    ):
        profile = await verify_linkedin_id_token("fake.jwt")

    assert profile["email_verified"] is True
