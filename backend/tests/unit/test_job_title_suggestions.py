"""Unit tests for resume-derived job title suggestions."""

from __future__ import annotations

import pytest

from app.agent import job_title_suggestions as jts


def test_extract_held_titles_from_experience() -> None:
    sections = {
        "experience": [
            {"title": "Mobile Developer", "company": "ShelfMark"},
            {"title": "Software Engineer", "company": "Acme"},
        ]
    }
    assert jts.extract_held_titles(sections) == [
        "Mobile Developer",
        "Software Engineer",
    ]


def test_heuristic_includes_mobile_titles_for_react_native_resume() -> None:
    resume = """
    ShelfMark — Mobile Developer
    Built a React Native book tracking app with 500 users.
    """
    held = ["Mobile Developer"]
    titles = jts._heuristic_suggestions(held_titles=held, resume_text=resume, count=10)
    assert "Mobile Developer" in titles
    assert any("React Native" in t or "Mobile" in t for t in titles)
    assert len(titles) == 10


def test_parse_llm_titles_accepts_json_array() -> None:
    raw = '["Backend Engineer", "Python Developer"]'
    assert jts._parse_llm_titles(raw) == ["Backend Engineer", "Python Developer"]


@pytest.mark.asyncio
async def test_suggest_job_titles_heuristic_without_llm() -> None:
    suggestions, held, source = await jts.suggest_job_titles(
        resume_text="Senior QA Engineer at TrustCo. Python automation.",
        parsed_sections={"experience": [{"title": "QA Engineer", "company": "TrustCo"}]},
        llm_client=None,
        count=10,
    )
    assert source == "heuristic"
    assert "QA Engineer" in held
    assert len(suggestions) == 10
