"""Unit tests for employer name resolution from job descriptions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.keywords import KeywordExtractionOutput, RoleContext
from app.models.rewrite import TailoredResumeOutput
from app.models.session import Session
from app.services.dashboard.resume_record import extract_jd_metadata, resolve_company_name

pytestmark = pytest.mark.unit

FISHER_JD = """Senior AI Developer
Fisher Investments
Camas, Washington
Apply Now
Save Job
This is an exciting and pivotal time to join Fisher Investments. Our Technology & Transformation organization is expanding its Generative AI capabilities.

Why Fisher Investments:

We work for a bigger purpose: bettering the investment universe. We take great pride in our inclusive culture, our learning and development framework customized for every employee, and our Great Place to Work Certification.
"""


def _session(jd: str) -> Session:
    return Session(
        session_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
        jd_raw=jd,
        phase3_output=TailoredResumeOutput(
            contact={"name": "Alex", "title": "Senior AI Developer"},
            summary="Experienced AI engineer.",
            skills=["Python"],
        ),
    )


def test_resolve_company_name_from_second_line() -> None:
    session = _session(FISHER_JD)
    assert resolve_company_name(session) == "Fisher Investments"


def test_extract_jd_metadata_uses_fisher_company() -> None:
    session = _session(FISHER_JD)
    title, company = extract_jd_metadata(session)
    assert company == "Fisher Investments"
    assert title == "Senior AI Developer"


def test_resolve_company_name_from_at_pattern() -> None:
    session = _session("Senior Engineer at Acme Corp\nBuild distributed systems.")
    assert resolve_company_name(session) == "Acme Corp"


def test_resolve_company_name_unknown_when_no_signal() -> None:
    session = _session("Looking for a strong communicator.")
    assert resolve_company_name(session) == "Unknown"
