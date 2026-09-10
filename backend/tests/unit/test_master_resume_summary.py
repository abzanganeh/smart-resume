"""Unit tests for human-readable master resume summaries."""

from __future__ import annotations

import pytest

from app.services.master_resume.summary import summarize_parsed_sections

pytestmark = pytest.mark.unit


def test_summarize_roles_schools_projects() -> None:
    text = summarize_parsed_sections(
        {
            "experience": [{"title": "Eng"}, {"title": "Lead"}],
            "education": [{"degree": "BS"}],
            "project": [{"name": "A"}, {"name": "B"}],
        }
    )
    assert text == "2 roles · 1 school · 2 projects"


def test_summarize_section_fallback() -> None:
    text = summarize_parsed_sections(
        {"summary": "Staff engineer.", "skills": ["Python"]}
    )
    assert text == "2 sections"


def test_summarize_empty() -> None:
    assert summarize_parsed_sections({}) is None
    assert summarize_parsed_sections(None) is None
