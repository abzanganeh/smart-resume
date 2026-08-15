"""Regression tests: empty/whitespace-only bullets must never render as
bare bullet points in any export format."""

from __future__ import annotations

import io

from docx import Document

from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput
from app.models.session import Session
from app.services.export_service import _resume_to_html, render_docx, render_txt

_BULLETS_WITH_BLANKS = ["Real bullet", "", "  ", "Another real bullet"]


def _session_with_blank_bullets() -> Session:
    return Session(
        session_id="test-session",
        phase3_output=TailoredResumeOutput(
            contact={"name": "Jane Doe"},
            experience=[TailoredExperienceEntry(company="Acme", bullets=_BULLETS_WITH_BLANKS)],
        ),
    )


def test_render_txt_skips_blank_bullets() -> None:
    text = render_txt(_session_with_blank_bullets())
    bullet_lines = [line for line in text.splitlines() if line.strip().startswith("•")]
    assert len(bullet_lines) == 2
    assert "Real bullet" in bullet_lines[0]
    assert "Another real bullet" in bullet_lines[1]


def test_render_docx_skips_blank_bullets() -> None:
    docx_bytes = render_docx(_session_with_blank_bullets())
    doc = Document(io.BytesIO(docx_bytes))
    bullet_paragraphs = [p for p in doc.paragraphs if p.style.name == "List Bullet"]
    assert len(bullet_paragraphs) == 2
    assert bullet_paragraphs[0].text == "Real bullet"
    assert bullet_paragraphs[1].text == "Another real bullet"


def test_resume_html_skips_blank_bullets() -> None:
    html = _resume_to_html(_session_with_blank_bullets())
    assert html.count("<li>") == 2
    assert "<li></li>" not in html
