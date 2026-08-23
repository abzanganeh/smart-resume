"""Local Mailpit SMTP delivery when Resend is not configured."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.config import settings
from app.services.auth.email import send_password_reset_email


class _FakeSMTP:
    last: dict[str, Any] = {}

    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        self.last["host"] = host
        self.last["port"] = port
        self.last["timeout"] = timeout

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def send_message(self, msg: Any) -> None:
        self.last["to"] = msg["To"]
        self.last["subject"] = msg["Subject"]
        self.last["from"] = msg["From"]


@pytest.mark.asyncio
async def test_password_reset_uses_smtp_when_resend_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeSMTP.last = {}
    monkeypatch.setattr(settings, "AUTH_SECRET", "0" * 64)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "SMTP_PORT", 31025)
    monkeypatch.setattr("app.services.auth.email.smtplib.SMTP", _FakeSMTP)

    result = await send_password_reset_email(
        to_email="reset-me@example.com",
        user_id=uuid.uuid4(),
        display_name="Reset Me",
    )

    assert result["sent"] is True
    assert result["provider"] == "smtp"
    assert result["token"]
    assert _FakeSMTP.last["host"] == "127.0.0.1"
    assert _FakeSMTP.last["port"] == 31025
    assert _FakeSMTP.last["to"] == "reset-me@example.com"
    assert "Reset" in str(_FakeSMTP.last["subject"])


@pytest.mark.asyncio
async def test_password_reset_logs_only_without_resend_or_smtp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "AUTH_SECRET", "0" * 64)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(settings, "SMTP_HOST", "")

    result = await send_password_reset_email(
        to_email="reset-me@example.com",
        user_id=uuid.uuid4(),
    )

    assert result["sent"] is False
    assert result["provider"] == "dev-log"
    assert result["token"]
