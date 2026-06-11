"""Unit tests for export download filename generation."""

from __future__ import annotations

from types import SimpleNamespace

from app.models.rewrite import TailoredResumeOutput
from app.services.export_service import export_attachment_filename


def _session(
    *,
    jd_raw: str = "",
    name: str = "Jane Doe",
    company: str | None = None,
) -> SimpleNamespace:
    contact = {"name": name}
    if company:
        contact["company"] = company
    return SimpleNamespace(
        jd_raw=jd_raw,
        phase3_output=TailoredResumeOutput(
            contact=contact,
            summary="",
            experience=[],
            skills=[],
            education=[],
        ),
        user_info=None,
        resume_parsed=None,
        company_intel=None,
    )


def test_export_filename_uses_company_when_jd_present() -> None:
    session = _session(
        jd_raw="Software Engineer at Stripe\nBuild payments.",
        company="Stripe",
    )
    assert export_attachment_filename(session, "pdf") == "stripe_resume.pdf"


def test_export_filename_uses_candidate_name_without_jd() -> None:
    session = _session(jd_raw="", name="Jane Doe")
    assert export_attachment_filename(session, "pdf") == "jane_doe_resume.pdf"


def test_export_filename_falls_back_to_candidate_when_company_unknown() -> None:
    session = _session(jd_raw="Some JD text", name="Jane Doe")
    assert export_attachment_filename(session, "pdf") == "jane_doe_resume.pdf"
