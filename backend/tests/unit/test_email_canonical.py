"""Unit tests for provider-aware email canonicalization."""

from __future__ import annotations

import pytest

from app.services.auth.email_canonical import canonicalize_email

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ali@gmail.com", "ali@gmail.com"),
        ("a.l.i@gmail.com", "ali@gmail.com"),
        ("ali+2@gmail.com", "ali@gmail.com"),
        ("ali+tag@googlemail.com", "ali@gmail.com"),
        ("a.b+tag@outlook.com", "a.b@outlook.com"),
        ("a.b@outlook.com", "a.b@outlook.com"),
        ("user+alias@yahoo.com", "user@yahoo.com"),
        ("user+alias@idme24.com", "user+alias@idme24.com"),
        ("a.b@idme24.com", "a.b@idme24.com"),
    ],
)
def test_canonicalize_email(raw: str, expected: str) -> None:
    assert canonicalize_email(raw) == expected
