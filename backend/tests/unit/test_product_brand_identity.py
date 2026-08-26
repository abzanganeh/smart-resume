"""Regression: transactional email and outbound Career Watch identity."""

import pytest

from app.brand import PRODUCT_NAME, PRODUCT_SITE_URL
from app.services.auth.email import (
    send_account_deleted_email,
    send_password_reset_email,
    send_verification_email,
)
from app.services.career_watch.fetch import CAREER_WATCH_USER_AGENT


def test_career_watch_user_agent_carries_flintapply_identity() -> None:
    assert PRODUCT_NAME in CAREER_WATCH_USER_AGENT
    assert PRODUCT_SITE_URL in CAREER_WATCH_USER_AGENT
    assert "flintresume" not in CAREER_WATCH_USER_AGENT.lower()
    assert "TalioCV" not in CAREER_WATCH_USER_AGENT


@pytest.mark.asyncio
async def test_verification_email_subject_uses_product_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uuid import uuid4

    captured: dict[str, str] = {}

    async def fake_send(to_email, subject, body_text, body_html, **kwargs):
        captured["subject"] = subject
        return {"sent": False, "provider": "dev-log", "token": kwargs.get("token", "")}

    monkeypatch.setattr(
        "app.services.auth.email._send",
        fake_send,
    )

    await send_verification_email(
        to_email="user@example.com",
        user_id=uuid4(),
    )
    assert captured["subject"] == f"Verify your {PRODUCT_NAME} email"
    assert "TalioCV" not in captured["subject"]


@pytest.mark.asyncio
async def test_password_reset_email_subject_uses_product_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uuid import uuid4

    captured: dict[str, str] = {}

    async def fake_send(to_email, subject, body_text, body_html, **kwargs):
        captured["subject"] = subject
        return {"sent": False, "provider": "dev-log", "token": kwargs.get("token", "")}

    monkeypatch.setattr("app.services.auth.email._send", fake_send)

    await send_password_reset_email(to_email="user@example.com", user_id=uuid4())
    assert captured["subject"] == f"Reset your {PRODUCT_NAME} password"


@pytest.mark.asyncio
async def test_account_deleted_email_subject_uses_product_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    async def fake_send(to_email, subject, body_text, body_html, **kwargs):
        captured["subject"] = subject
        return {"sent": False, "provider": "dev-log", "token": kwargs.get("token", "")}

    monkeypatch.setattr("app.services.auth.email._send", fake_send)

    await send_account_deleted_email(to_email="user@example.com")
    assert captured["subject"] == f"Your {PRODUCT_NAME} account has been deleted"
