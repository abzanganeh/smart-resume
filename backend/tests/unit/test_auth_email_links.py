"""Lock the URLs embedded in verification and password-reset emails."""

from uuid import uuid4

import pytest

from app.services.auth.email import password_reset_link, verification_link


def test_password_reset_link_points_at_frontend_reset_page() -> None:
    link = password_reset_link("abc.def")
    assert "/auth/reset?token=abc.def" in link


def test_verification_link_points_at_frontend_verify_page() -> None:
    link = verification_link("abc.def")
    assert "/auth/verify?token=abc.def" in link


def test_make_password_reset_token_is_unique(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings
    from app.services.auth.email import make_password_reset_token

    monkeypatch.setattr(settings, "AUTH_SECRET", "0" * 64)
    user_id = uuid4()
    assert make_password_reset_token(user_id) != make_password_reset_token(user_id)
