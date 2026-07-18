"""Unit tests for autofill payload mapping."""

from __future__ import annotations

from app.models.rewrite import TailoredResumeOutput
from app.models.session import Session
from app.services.autofill import (
    build_autofill_fields,
    detect_platform,
    extract_contact,
    split_name,
)


def test_detect_platform_from_host() -> None:
    assert detect_platform("https://boards.greenhouse.io/acme/jobs/123") == "greenhouse"
    assert detect_platform("https://www.linkedin.com/jobs/view/123") == "linkedin"
    assert detect_platform("https://example.com/jobs/1") == "unknown"


def test_split_name() -> None:
    assert split_name("Alex Rivera") == ("Alex", "Rivera")
    assert split_name("Alex") == ("Alex", "")


def test_build_greenhouse_fields_from_contact() -> None:
    fields = build_autofill_fields(
        {
            "name": "Alex Rivera",
            "email": "alex@example.com",
            "phone": "555-0100",
            "linkedin": "https://www.linkedin.com/in/alex",
        },
        "greenhouse",
    )
    keys = {field["key"] for field in fields}
    assert keys == {"first_name", "last_name", "email", "phone", "linkedin_url", "resume"}
    email = next(field for field in fields if field["key"] == "email")
    assert email["value"] == "alex@example.com"
    assert "job_application[email]" in email["selector"]


def test_build_unknown_platform_fields_use_empty_selectors() -> None:
    fields = build_autofill_fields(
        {
            "name": "Alex Rivera",
            "email": "alex@example.com",
            "phone": "555-0100",
            "linkedin": "https://www.linkedin.com/in/alex",
        },
        "unknown",
    )
    keys = {field["key"] for field in fields}
    assert keys == {"first_name", "last_name", "email", "phone", "linkedin_url", "resume"}
    assert all(field["selector"] == "" for field in fields)
    email = next(field for field in fields if field["key"] == "email")
    assert email["value"] == "alex@example.com"
    resume = next(field for field in fields if field["key"] == "resume")
    assert resume["value"] == ""


def test_build_linkedin_platform_fields_use_empty_selectors() -> None:
    fields = build_autofill_fields(
        {"name": "Alex Rivera", "email": "alex@example.com"},
        "linkedin",
    )
    keys = {field["key"] for field in fields}
    assert keys == {"first_name", "last_name", "email", "resume"}
    assert all(field["selector"] == "" for field in fields)


def test_build_fields_skips_missing_contact_values() -> None:
    fields = build_autofill_fields({"email": "alex@example.com"}, "unknown")
    keys = {field["key"] for field in fields}
    assert keys == {"email", "resume"}


def test_extract_contact_prefers_phase3_output() -> None:
    session = Session(
        session_id="sess-1",
        phase3_output=TailoredResumeOutput(
            contact={"name": "Sam Lee", "email": "sam@example.com"},
            summary="Tailored summary only.",
        ),
    )
    contact = extract_contact(session)
    assert contact["email"] == "sam@example.com"
    assert "Tailored summary only." not in contact.values()
