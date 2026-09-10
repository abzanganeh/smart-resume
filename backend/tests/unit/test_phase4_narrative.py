"""Tests for Phase 4 narrative category synthesis (no LLM)."""

from __future__ import annotations

from dataclasses import replace

from app.agent.phase4_narrative import (
    _sanitize_headline,
    build_category_summaries,
    clear_narrative_cache_for_tests,
    narrative_cache_key,
)
from app.agent.phase4_score import AxisScore, ResumeQualityResult, compute_ats_score
from app.models.rewrite import TailoredEducationEntry, TailoredResumeOutput


def _score_result(**kwargs) -> ResumeQualityResult:
    resume = TailoredResumeOutput(
        contact={"name": "Jane", "email": "jane@example.com"},
        summary="Engineer.",
        skills=["Languages: Python"],
        experience=[],
        projects=kwargs.pop("projects", []),
        education=kwargs.pop("education", []),
    )
    return compute_ats_score(resume, ["Python"])


def test_build_category_summaries_groups_axes() -> None:
    result = _score_result(
        projects=[{"name": "", "description": "Tool", "bullets": []}],
        education=[TailoredEducationEntry(degree="B.S.", institution="", year="2020")],
    )
    summaries = build_category_summaries(result)
    assert len(summaries) == 3
    keys = {item.category_key for item in summaries}
    assert keys == {"relevance", "impact", "style"}
    style = next(item for item in summaries if item.category_key == "style")
    assert style.severity in ("urgent", "critical", "minor")
    assert style.issue_count >= 1


def test_narrative_cache_key_stable_for_same_axes() -> None:
    result = _score_result()
    key_a = narrative_cache_key(result.ats_score, result.axes)
    key_b = narrative_cache_key(result.ats_score, result.axes)
    assert key_a == key_b


def test_narrative_cache_key_changes_when_axis_status_changes() -> None:
    pass_axis = AxisScore(
        key="bullet_metrics",
        label="Quantified bullets",
        score=15,
        max_score=15,
        status="pass",
        summary="ok",
    )
    fail_axis = replace(pass_axis, status="fail", score=0)
    result = _score_result()
    key_pass = narrative_cache_key(result.ats_score, [pass_axis])
    key_fail = narrative_cache_key(result.ats_score, [fail_axis])
    assert key_pass != key_fail


def test_narrative_cache_key_changes_with_target_role() -> None:
    result = _score_result()
    key_a = narrative_cache_key(result.ats_score, result.axes, "Engineer")
    key_b = narrative_cache_key(result.ats_score, result.axes, "Director")
    assert key_a != key_b


def test_sanitize_headline_preserves_long_copy() -> None:
    result = _score_result()
    categories = build_category_summaries(result)
    long = (
        "The resume demonstrates solid technical foundations for a Forward Deployed Engineer role "
        "but suffers from missing core keywords alongside unquantified achievements. "
        "Improving keyword density and metric-driven bullet points will significantly elevate interview readiness."
    )
    cleaned = _sanitize_headline(
        long,
        score_result=result,
        target_role="Engineer",
        categories=categories,
    )
    assert len(cleaned) > 220
    assert "interview readiness" in cleaned.lower()


def test_sanitize_headline_rejects_degenerate_repetition() -> None:
    result = _score_result()
    categories = build_category_summaries(result)
    repeated = " ".join(["Improve keyword placement"] * 20)
    cleaned = _sanitize_headline(
        repeated,
        score_result=result,
        target_role="Engineer",
        categories=categories,
    )
    assert cleaned.count("Improve keyword placement") <= 2
    assert "61/100" in cleaned or "scores" in cleaned.lower()


def teardown_module() -> None:
    clear_narrative_cache_for_tests()
