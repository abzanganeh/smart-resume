"""Lock the URLs embedded in verification and password-reset emails."""

from app.services.auth.email import password_reset_link, verification_link


def test_password_reset_link_points_at_frontend_reset_page() -> None:
    link = password_reset_link("abc.def")
    assert "/auth/reset?token=abc.def" in link


def test_verification_link_points_at_frontend_verify_page() -> None:
    link = verification_link("abc.def")
    assert "/auth/verify?token=abc.def" in link
