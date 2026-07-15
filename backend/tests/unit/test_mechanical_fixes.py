"""Tests for mechanical keyword insertion."""

from __future__ import annotations

from app.agent.mechanical_fixes import apply_keyword_to_skills, extract_missing_keyword
from app.models.qa import BlockingIssue
from app.models.rewrite import TailoredResumeOutput


def test_extract_missing_keyword_from_suggestion() -> None:
    issue = BlockingIssue(
        category="keyword",
        description="Missing",
        suggestion="Add 'Kubernetes' to the Skills section AND reinforce it in an Experience bullet.",
        impact="high",
        fix_effort="one_click",
    )
    assert extract_missing_keyword(issue) == "Kubernetes"


def test_apply_keyword_to_skills_appends_to_category_line() -> None:
    tailored = TailoredResumeOutput(skills=["Languages: Python, SQL"])
    issue = BlockingIssue(
        category="keyword",
        description="Missing",
        suggestion="Add 'Kubernetes' to the Skills section AND reinforce it.",
        impact="high",
        fix_effort="one_click",
    )
    keyword = extract_missing_keyword(issue)
    assert keyword is not None
    updated = apply_keyword_to_skills(tailored, keyword)
    assert updated is not None
    assert "Kubernetes" in updated.skills[0]
