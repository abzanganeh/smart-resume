"""OAuth provider enum covers extended SSO backends."""

from __future__ import annotations

from app.models.user import AuthProvider


def test_auth_provider_includes_microsoft_linkedin_apple() -> None:
    values = {p.value for p in AuthProvider}
    assert {"microsoft", "linkedin", "apple"}.issubset(values)
