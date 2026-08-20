"""Unit tests for deterministic job-title fit insights."""

from __future__ import annotations

from app.agent.title_fit_insights import enrich_title_suggestions, score_title_fit


def test_held_title_scores_highest() -> None:
    resume = "Mobile Developer at ShelfMark. React Native app with 500 users."
    held = ["Mobile Developer"]
    insight = score_title_fit(
        "Mobile Developer",
        resume_text=resume,
        held_titles=held,
    )
    assert insight.fit_score >= 85
    assert any("held this title" in s.lower() for s in insight.strengths)


def test_adjacent_title_has_strengths_and_bounded_score() -> None:
    resume = "Built React Native apps. JavaScript, TypeScript, mobile UI."
    held = ["Mobile Developer"]
    insight = score_title_fit(
        "React Native Developer",
        resume_text=resume,
        held_titles=held,
    )
    assert 60 <= insight.fit_score <= 98
    assert insight.strengths
    assert len(insight.weaknesses) <= 2


def test_senior_title_without_senior_resume_adds_weakness() -> None:
    resume = "Junior QA Engineer. Python scripts for test automation."
    held = ["QA Engineer"]
    insight = score_title_fit(
        "Senior Backend Engineer",
        resume_text=resume,
        held_titles=held,
    )
    assert insight.fit_score < 80
    assert any("senior" in w.lower() for w in insight.weaknesses)


def test_enrich_sorts_by_fit_score_descending() -> None:
    resume = "Python FastAPI backend engineer. PostgreSQL, Redis, AWS."
    held = ["Backend Engineer"]
    titles = [
        "Frontend Engineer",
        "Backend Engineer",
        "Machine Learning Engineer",
    ]
    rows = enrich_title_suggestions(
        titles,
        resume_text=resume,
        held_titles=held,
    )
    assert rows[0].title == "Backend Engineer"
    assert rows[0].fit_score >= rows[1].fit_score >= rows[2].fit_score
