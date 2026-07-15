"""Deterministic ATS scoring engine tests.

These tests pin the score curve to specific resume shapes so a regression
in the weights or detection logic shows up immediately. The engine has 12
axes whose weights total 100; any change to those weights must update both
the engine and these tests in lockstep.
"""
from __future__ import annotations

import pytest

from app.agent.phase4_score import (
    AxisScore,
    ResumeQualityResult,
    compute_ats_score,
)
from app.models.rewrite import (
    TailoredEducationEntry,
    TailoredExperienceEntry,
    TailoredResumeOutput,
)


def _resume(
    *,
    summary: str = "Senior engineer.",
    skills: list[str] | None = None,
    experience: list[dict] | None = None,
    contact: dict | None = None,
    projects: list[dict] | None = None,
    education: list[dict] | None = None,
) -> TailoredResumeOutput:
    return TailoredResumeOutput(
        contact=contact or {"name": "Jane Doe", "email": "jane@example.com"},
        summary=summary,
        skills=skills or [],
        experience=[TailoredExperienceEntry(**e) for e in (experience or [])],
        education=[TailoredEducationEntry(**e) for e in (education or [])],
        projects=projects or [],
        certifications=[],
    )


def _axis(result: ResumeQualityResult, key: str) -> AxisScore:
    for axis in result.axes:
        if axis.key == key:
            return axis
    raise AssertionError(f"Axis {key!r} not found in result")


def test_score_is_deterministic_for_same_input() -> None:
    resume = _resume(
        summary="Built Python and SQL pipelines",
        skills=["Languages: Python, SQL", "Cloud: AWS, Docker"],
        experience=[
            {
                "title": "ML Engineer",
                "company": "Acme",
                "dates": "2022-2025",
                "bullets": ["Shipped Python service handling 1M req/day across AWS infrastructure"],
            }
        ],
    )
    keywords = ["Python", "SQL", "AWS", "Docker"]

    first = compute_ats_score(resume, keywords)
    second = compute_ats_score(resume, keywords)

    assert first.ats_score == second.ats_score
    assert first.breakdown == second.breakdown


def test_full_keyword_coverage_with_dual_placement_scores_high() -> None:
    resume = _resume(
        summary="Senior engineer experienced with Python, AWS, and Kubernetes infrastructure.",
        skills=[
            "Languages: Python, Go",
            "Cloud: AWS, Kubernetes, Docker",
        ],
        experience=[
            {
                "title": "Lead Engineer",
                "company": "Acme",
                "dates": "2022-2025",
                "bullets": [
                    "Built Python service on AWS reducing latency by 30% across 500 endpoints",
                    "Migrated 12 Kubernetes workloads with zero downtime saving $200K annually",
                ],
            }
        ],
    )
    result = compute_ats_score(resume, ["Python", "AWS", "Kubernetes"])
    assert result.ats_score >= 90
    assert result.missing_keywords == []
    assert result.single_section_keywords == []


def test_missing_keywords_lowers_score_and_lists_them() -> None:
    resume = _resume(
        summary="Engineer.",
        skills=["Languages: Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "Acme",
                "dates": "2024",
                "bullets": ["Wrote code."],
            }
        ],
    )
    result = compute_ats_score(resume, ["Python", "Kubernetes", "Terraform", "AWS"])
    # Only 1 of 4 keywords present (Python).
    assert set(result.missing_keywords) == {"Kubernetes", "Terraform", "AWS"}
    presence = _axis(result, "keyword_presence")
    # 1/4 keywords present => 7.5 of 30 points.
    assert presence.score == pytest.approx(7.5)
    assert presence.status == "fail"


def test_single_section_keyword_does_not_earn_dual_placement_points() -> None:
    resume = _resume(
        summary="General software engineer.",
        skills=["Languages: Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "Acme",
                "dates": "2024",
                "bullets": ["Built dashboards."],
            }
        ],
    )
    result = compute_ats_score(resume, ["Python"])
    assert "Python" in result.single_section_keywords
    presence = _axis(result, "keyword_presence")
    dual = _axis(result, "keyword_dual_placement")
    assert presence.score == pytest.approx(30.0)  # full credit for presence
    assert dual.score == pytest.approx(0.0)


def test_unquantified_bullets_lose_metric_points() -> None:
    resume = _resume(
        summary="Engineer with Python.",
        skills=["Languages: Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "Acme",
                "dates": "2024",
                "bullets": [
                    "Built things in Python.",
                    "Maintained services.",
                ],
            }
        ],
    )
    result = compute_ats_score(resume, ["Python"])
    metrics = _axis(result, "bullet_metrics")
    assert metrics.score == pytest.approx(0.0)
    assert metrics.status == "fail"


def test_action_verbs_axis_credits_strong_openers() -> None:
    resume = _resume(
        skills=["Languages: Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "Acme",
                "dates": "2024",
                "bullets": [
                    "Shipped a Python ETL pipeline serving 10M rows daily across 4 regions",
                    "Reduced cloud spend by 38% through aggressive instance right-sizing",
                ],
            }
        ],
    )
    result = compute_ats_score(resume, ["Python"])
    axis = _axis(result, "action_verbs")
    assert axis.status == "pass"
    assert axis.score == pytest.approx(10.0)


def test_weak_phrase_axis_penalizes_responsible_for() -> None:
    resume = _resume(
        skills=["Languages: Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "Acme",
                "dates": "2024",
                "bullets": [
                    "Responsible for maintaining the customer database",
                    "Worked on internal tools and dashboards for the team",
                    "Helped with onboarding new engineers",
                ],
            }
        ],
    )
    result = compute_ats_score(resume, ["Python"])
    axis = _axis(result, "weak_phrases")
    assert axis.status == "fail"
    assert axis.score < 5
    assert any("responsible for" in issue.lower() for issue in axis.issues)


def test_first_person_axis_flags_pronouns() -> None:
    resume = _resume(
        summary="I am a passionate engineer who loves shipping code.",
        skills=["Languages: Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "Acme",
                "dates": "2024",
                "bullets": ["I built a service handling 1M req/day"],
            }
        ],
    )
    result = compute_ats_score(resume, ["Python"])
    axis = _axis(result, "first_person")
    assert axis.status in ("warn", "fail")
    assert axis.score < 5


def test_buzzword_axis_flags_cliches() -> None:
    resume = _resume(
        summary="Detail-oriented team player who is a self-starter.",
        skills=["Languages: Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "Acme",
                "dates": "2024",
                "bullets": ["Shipped Python service handling 1M req/day"],
            }
        ],
    )
    result = compute_ats_score(resume, ["Python"])
    axis = _axis(result, "buzzwords")
    assert axis.status != "pass"
    assert any(b in (axis.summary or "").lower() for b in ("team player", "self-starter", "detail-oriented"))


def test_bullet_length_axis_flags_short_and_long_bullets() -> None:
    long_bullet = (
        "Built and maintained a complex distributed system spanning multiple cloud "
        "regions and integrating dozens of third-party APIs while ensuring high "
        "availability across all services and customer touchpoints throughout."
    )
    resume = _resume(
        skills=["Languages: Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "Acme",
                "dates": "2024",
                "bullets": ["Shipped code", long_bullet],
            }
        ],
    )
    result = compute_ats_score(resume, ["Python"])
    axis = _axis(result, "bullet_length")
    assert axis.status != "pass"


def test_field_completeness_passes_when_no_projects_or_education() -> None:
    resume = _resume(
        skills=["Languages: Python"],
        experience=[
            {"title": "Engineer", "company": "Acme", "dates": "2024", "bullets": ["Shipped Python service handling 1M req/day"]}
        ],
    )
    result = compute_ats_score(resume, ["Python"])
    axis = _axis(result, "field_completeness")
    assert axis.status == "pass"
    assert axis.issues == []


def test_field_completeness_flags_project_missing_name_and_education_missing_institution() -> None:
    resume = _resume(
        skills=["Languages: Python"],
        experience=[
            {"title": "Engineer", "company": "Acme", "dates": "2024", "bullets": ["Shipped Python service handling 1M req/day"]}
        ],
        projects=[{"name": "", "description": "A tool", "bullets": []}],
        education=[{"degree": "B.S. CS", "institution": "", "year": "2020"}],
    )
    result = compute_ats_score(resume, ["Python"])
    axis = _axis(result, "field_completeness")
    assert axis.status == "fail"
    assert len(axis.issues) == 2
    assert any("project" in issue.lower() for issue in axis.issues)
    assert any("education" in issue.lower() for issue in axis.issues)


def test_field_completeness_passes_when_all_entries_have_required_fields() -> None:
    resume = _resume(
        skills=["Languages: Python"],
        experience=[
            {"title": "Engineer", "company": "Acme", "dates": "2024", "bullets": ["Shipped Python service handling 1M req/day"]}
        ],
        projects=[{"name": "Churn Predictor", "description": "ML pipeline", "bullets": []}],
        education=[{"degree": "B.S. CS", "institution": "State University", "year": "2020"}],
    )
    result = compute_ats_score(resume, ["Python"])
    axis = _axis(result, "field_completeness")
    assert axis.status == "pass"
    assert axis.issues == []


def test_score_axes_total_to_one_hundred() -> None:
    resume = _resume(
        summary="Senior engineer.",
        skills=["Languages: Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "Acme",
                "dates": "2024",
                "bullets": ["Shipped a service handling 1M req/day on AWS"],
            }
        ],
    )
    result = compute_ats_score(resume, ["Python"])
    assert sum(axis.max_score for axis in result.axes) == pytest.approx(100.0)


def test_ceiling_is_at_least_score_and_capped_at_one_hundred() -> None:
    resume = _resume(
        summary="Engineer.",
        skills=[],
        experience=[],
        contact={},
    )
    result = compute_ats_score(resume, ["Python", "AWS"])
    assert result.score_ceiling >= result.ats_score
    assert result.score_ceiling <= 100


def test_engine_payload_is_serializable() -> None:
    """Sanity check: the to_payload() shape matches what QAOutput expects."""
    resume = _resume(
        skills=["Languages: Python"],
        experience=[
            {"title": "Engineer", "company": "Acme", "dates": "2024", "bullets": ["Shipped Python service handling 1M reqs"]}
        ],
    )
    payload = compute_ats_score(resume, ["Python"]).to_payload()
    assert "ats_score" in payload
    assert "score_ceiling" in payload
    assert isinstance(payload["axes"], list)
    assert all({"key", "label", "score", "max", "status", "summary", "issues"} <= a.keys() for a in payload["axes"])
