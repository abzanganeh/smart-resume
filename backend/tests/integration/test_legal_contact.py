"""Integration tests for the legal / DPO contact endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


_VALID_PAYLOAD = {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "topic": "data_subject_request",
    "message": "Please export the data associated with my account.",
}


async def test_dpo_contact_returns_200_and_logs_when_resend_unconfigured(
    app_client: AsyncClient,
) -> None:
    """Without RESEND_API_KEY, the route still 200s and reports dev-log."""

    with patch("app.routers.legal.settings") as mock_settings:
        mock_settings.RESEND_API_KEY = ""
        mock_settings.RESEND_FROM_EMAIL = "noreply@zanganehai.com"

        r = await app_client.post("/api/legal/dpo-contact", json=_VALID_PAYLOAD)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["delivered"] is False
    assert body["provider"] == "dev-log"


async def test_dpo_contact_calls_resend_when_configured(
    app_client: AsyncClient,
) -> None:
    """When RESEND_API_KEY is set, the route forwards to Resend."""

    sent_payloads: list[dict] = []

    def _fake_send(payload: dict) -> dict:
        sent_payloads.append(payload)
        return {"id": "re_test_123"}

    fake_resend = type(
        "FakeResend",
        (),
        {"api_key": None, "Emails": type("E", (), {"send": staticmethod(_fake_send)})},
    )()

    with patch("app.routers.legal.settings") as mock_settings, patch.dict(
        "sys.modules", {"resend": fake_resend}
    ):
        mock_settings.RESEND_API_KEY = "re_live_test"
        mock_settings.RESEND_FROM_EMAIL = "noreply@zanganehai.com"
        r = await app_client.post("/api/legal/dpo-contact", json=_VALID_PAYLOAD)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["delivered"] is True
    assert body["provider"] == "resend"
    assert len(sent_payloads) == 1
    sent = sent_payloads[0]
    assert sent["to"] == ["privacy@zanganehai.com"]
    assert sent["reply_to"] == ["jane@example.com"]
    assert "data_subject_request" in sent["subject"]


async def test_dpo_contact_validates_minimum_message_length(
    app_client: AsyncClient,
) -> None:
    """Messages under 20 characters are rejected with 422."""

    payload = {**_VALID_PAYLOAD, "message": "too short"}
    r = await app_client.post("/api/legal/dpo-contact", json=payload)
    assert r.status_code == 422, r.text


async def test_dpo_contact_validates_email(
    app_client: AsyncClient,
) -> None:
    payload = {**_VALID_PAYLOAD, "email": "not-an-email"}
    r = await app_client.post("/api/legal/dpo-contact", json=payload)
    assert r.status_code == 422, r.text
