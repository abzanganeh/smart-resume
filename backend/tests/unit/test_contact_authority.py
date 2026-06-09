"""Unit tests for authoritative contact merge (anti-hallucination)."""

from __future__ import annotations

from app.models.rewrite import TailoredResumeOutput
from app.models.userinfo import UserInfo
from app.services.contact_authority import apply_authoritative_contact, authoritative_contact


def test_account_email_overrides_llm_hallucination() -> None:
    merged = authoritative_contact(
        {"name": "Alireza", "email": "alireza.zanganeh@gmail.com"},
        user_info=UserInfo(name="Alireza Barzin", email="alireza@zanganehai.com"),
        account_email="alireza@zanganehai.com",
    )
    assert merged["email"] == "alireza@zanganehai.com"


def test_user_info_email_overrides_llm_when_no_account_email() -> None:
    merged = authoritative_contact(
        {"email": "wrong@gmail.com"},
        user_info=UserInfo(email="alireza@zanganehai.com"),
    )
    assert merged["email"] == "alireza@zanganehai.com"


def test_llm_email_kept_when_no_user_sources() -> None:
    merged = authoritative_contact({"email": "from-resume@company.com"})
    assert merged["email"] == "from-resume@company.com"


def test_placeholder_email_not_used_without_user_sources() -> None:
    merged = authoritative_contact({"email": "john.doe@example.com"})
    assert merged["email"] == ""


def test_apply_authoritative_contact_updates_tailored_output() -> None:
    output = TailoredResumeOutput(
        contact={"email": "hallucinated@gmail.com"},
        summary="Engineer",
    )
    fixed = apply_authoritative_contact(
        output,
        account_email="alireza@zanganehai.com",
    )
    assert fixed.contact["email"] == "alireza@zanganehai.com"


def test_tailored_name_wins_when_user_renames_for_export() -> None:
    merged = authoritative_contact(
        {"name": "Ali Barzin", "email": "alireza@zanganehai.com"},
        user_info=UserInfo(name="Alireza Barzin Zanganeh", email="alireza@zanganehai.com"),
        account_email="alireza@zanganehai.com",
    )
    assert merged["name"] == "Ali Barzin"
    assert merged["email"] == "alireza@zanganehai.com"


def test_profile_name_used_when_tailored_matches() -> None:
    merged = authoritative_contact(
        {"name": "Alireza Barzin Zanganeh"},
        user_info=UserInfo(name="Alireza Barzin Zanganeh"),
    )
    assert merged["name"] == "Alireza Barzin Zanganeh"
