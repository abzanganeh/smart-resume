from __future__ import annotations

import pytest

from app.services.contact_normalize import sanitize_contact_url
from app.services.jd_fetch import (
    assert_safe_fetch_url,
    infer_jd_title_from_text,
    parse_lever_posting_url,
)


def test_parse_lever_posting_url() -> None:
    url = "https://jobs.lever.co/apolloresearch/2237ce81-cb8e-4f53-a047-e12ea5d6e7d8"
    assert parse_lever_posting_url(url) == (
        "apolloresearch",
        "2237ce81-cb8e-4f53-a047-e12ea5d6e7d8",
    )


def test_infer_jd_title_skips_logo_line() -> None:
    text = "Apollo Research logo\nForward Deployed Engineer (Product)\n\nTHE OPPORTUNITY"
    assert infer_jd_title_from_text(text) == "Forward Deployed Engineer (Product)"


def test_sanitize_contact_url_rejects_label_only() -> None:
    assert sanitize_contact_url("linkedin", "LinkedIn") is None
    assert sanitize_contact_url("github", "Github") is None


def test_sanitize_contact_url_normalizes_bare_profile() -> None:
    assert sanitize_contact_url("linkedin", "linkedin.com/in/jane") == "https://linkedin.com/in/jane"
    assert sanitize_contact_url("github", "github.com/jane") == "https://github.com/jane"
    assert sanitize_contact_url("github", "jane") == "https://github.com/jane"


def test_sanitize_contact_url_rejects_dangerous_schemes() -> None:
    assert sanitize_contact_url("linkedin", "javascript:alert(1)") is None
    assert sanitize_contact_url("github", "data:text/html,evil") is None


def test_assert_safe_fetch_url_blocks_loopback() -> None:
    with pytest.raises(ValueError, match="not allowed|private|restricted"):
        assert_safe_fetch_url("http://127.0.0.1/jobs")


@pytest.mark.asyncio
async def test_fetch_jd_from_url_lever_api() -> None:
    from app.services.jd_fetch import fetch_jd_from_url

    url = "https://jobs.lever.co/apolloresearch/2237ce81-cb8e-4f53-a047-e12ea5d6e7d8"
    fetched = await fetch_jd_from_url(url, max_chars=60_000)
    assert fetched.title == "Forward Deployed Engineer (Product)"
    assert fetched.text.startswith("Forward Deployed Engineer (Product)")
    assert "THE OPPORTUNITY" in fetched.text
