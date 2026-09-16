"""Unit tests for resume record / tracker label helpers."""

from __future__ import annotations

import uuid

import pytest

from app.models.dashboard import ResumeRecord, ResumeRecordStatus, TailoringStage
from app.models.resume import ContactInfo, ParsedResume
from app.models.session import Session
from app.services.dashboard.resume_record import (
    apply_application_label_to_metadata,
    is_placeholder_record_company,
    is_placeholder_record_title,
    parse_application_label,
    resolve_record_tracker_title_company,
    sanitize_label_part,
)
from app.services.session_store import create_session

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Acme Health — Senior Backend", ("Acme Health", "Senior Backend")),
        ("Acme Health - Senior Backend", ("Acme Health", "Senior Backend")),
        ("Acme Health @ Senior Backend", ("Acme Health", "Senior Backend")),
        ("", (None, None)),
        ("   ", (None, None)),
        ("Senior Backend", (None, "Senior Backend")),
    ],
)
def test_parse_application_label(label: str, expected: tuple[str | None, str | None]) -> None:
    assert parse_application_label(label) == expected


def test_sanitize_label_part_strips_control_chars() -> None:
    assert sanitize_label_part("Acme\x00Health") == "AcmeHealth"


def test_is_placeholder_record_title_variants() -> None:
    assert is_placeholder_record_title("Resume draft")
    assert is_placeholder_record_title("Untitled role")
    assert is_placeholder_record_title("Jane - resume draft")
    assert not is_placeholder_record_title("Custom title", contact_name="Jane")
    assert is_placeholder_record_title("Jane — resume draft", contact_name="Jane")
    assert not is_placeholder_record_title("Senior Backend", contact_name="Jane")


def test_is_placeholder_record_company() -> None:
    assert is_placeholder_record_company("—")
    assert is_placeholder_record_company("unknown")
    assert is_placeholder_record_company("")
    assert not is_placeholder_record_company("Acme Health")


def test_apply_application_label_keeps_real_jd_metadata() -> None:
    session = Session(session_id="sess-1")
    title, company = apply_application_label_to_metadata(
        session,
        jd_title="Staff Backend Engineer",
        jd_company="Northwind Systems",
        app_label="Acme Health — Senior Backend",
    )
    assert title == "Staff Backend Engineer"
    assert company == "Northwind Systems"


@pytest.mark.asyncio
async def test_apply_application_label_replaces_placeholder_metadata() -> None:
    session = await create_session()
    session.resume_parsed = ParsedResume(contact=ContactInfo(name="Ali Barzin"))
    title, company = apply_application_label_to_metadata(
        session,
        jd_title="Ali Barzin — resume draft",
        jd_company="—",
        app_label="Acme Health — Senior Backend",
    )
    assert title == "Senior Backend"
    assert company == "Acme Health"


def test_resolve_record_tracker_title_company_prefers_display_name() -> None:
    record = ResumeRecord(
        user_id=uuid.uuid4(),
        session_id="sess-1",
        jd_title="Ali Barzin — resume draft",
        jd_company="—",
        jd_text_hash="abc",
        display_name="Acme Health — Senior Backend",
        tags=[],
        current_ats_score=0,
        starting_ats_score=0,
        status=ResumeRecordStatus.draft,
        tailoring_stage=TailoringStage.in_progress,
    )
    assert resolve_record_tracker_title_company(record) == (
        "Senior Backend",
        "Acme Health",
    )


def test_resolve_record_tracker_title_company_role_only_label() -> None:
    record = ResumeRecord(
        user_id=uuid.uuid4(),
        session_id="sess-1",
        jd_title="Staff Backend Engineer",
        jd_company="Northwind Systems",
        jd_text_hash="abc",
        display_name="Dream role",
        tags=[],
        current_ats_score=0,
        starting_ats_score=0,
        status=ResumeRecordStatus.draft,
        tailoring_stage=TailoringStage.in_progress,
    )
    assert resolve_record_tracker_title_company(record) == (
        "Dream role",
        "Northwind Systems",
    )


def test_resolve_record_tracker_title_company_empty_display_name_fallback() -> None:
    record = ResumeRecord(
        user_id=uuid.uuid4(),
        session_id="sess-1",
        jd_title="Staff Backend Engineer",
        jd_company="Northwind Systems",
        jd_text_hash="abc",
        display_name=None,
        tags=[],
        current_ats_score=0,
        starting_ats_score=0,
        status=ResumeRecordStatus.draft,
        tailoring_stage=TailoringStage.in_progress,
    )
    assert resolve_record_tracker_title_company(record) == (
        "Staff Backend Engineer",
        "Northwind Systems",
    )
