"""Misinformation guardrails (M23 C3 / OWASP LLM07).

TalioCV's never-fabricate-metrics rule must be enforceable in code, not prompt
hope alone. Phase 4 numeric ATS scores are deterministic; Phase 3 strips
LLM-invented metrics post-hoc.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.agent.phase3_truthfulness import validate_bullet_metrics
from app.agent.phase4_deterministic import compute_score_result
from app.agent.phase4_score import compute_ats_score
from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput
from app.models.session import ApprovedMetric

REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_BACKEND = REPO_ROOT / "backend"
PHASE4_QA = REPO_BACKEND / "app" / "agent" / "phase4_qa.py"
QUALITY_RULES = REPO_ROOT / ".cursor" / "rules" / "resume-quality.mdc"


def _resume_with_bullet(bullet: str) -> TailoredResumeOutput:
    return TailoredResumeOutput(
        experience=[
            TailoredExperienceEntry(
                title="Engineer",
                company="Acme",
                dates="2020-2024",
                bullets=[bullet],
            )
        ]
    )


def test_fabricated_metric_is_stripped_and_flagged() -> None:
    """LLM07 — invented percentages become metrics_needed, not resume text."""
    output = _resume_with_bullet("Improved throughput by 42% without approval.")
    approved: list[ApprovedMetric] = []
    result = validate_bullet_metrics(output, approved)
    assert "42%" not in result.experience[0].bullets[0]
    assert len(result.metrics_needed) == 1


def test_approved_metric_is_preserved() -> None:
    """LLM07 — verified metrics from the user stay in output."""
    output = _resume_with_bullet("Reduced defects by 15% through automation.")
    approved = [ApprovedMetric(scope="Acme", metric="reduced defects by 15%")]
    result = validate_bullet_metrics(output, approved)
    assert "15%" in result.experience[0].bullets[0]
    assert not result.metrics_needed


def test_phase4_score_is_deterministic_for_identical_input() -> None:
    """LLM07 — numeric ATS score must not vary run-to-run for the same résumé."""
    resume = TailoredResumeOutput(
        summary="Senior engineer with Python and AWS experience.",
        skills=["Languages: Python", "Cloud: AWS"],
        experience=[
            TailoredExperienceEntry(
                title="Engineer",
                company="Acme",
                dates="2020-2024",
                bullets=["Built Python services on AWS handling 1M requests daily."],
            )
        ],
    )
    keywords = ["Python", "AWS"]

    first = compute_ats_score(resume, keywords)
    second = compute_ats_score(resume, keywords)

    assert first.ats_score == second.ats_score
    assert first.breakdown == second.breakdown


def test_phase4_qa_overrides_llm_ats_score_with_deterministic_engine() -> None:
    """LLM07 — the score shown to users comes from ``phase4_score``, not the LLM."""
    source = PHASE4_QA.read_text(encoding="utf-8")
    assert "Override the LLM-generated score with the deterministic one" in source
    assert "score_result.ats_score" in source


def test_compute_score_result_delegates_to_deterministic_engine() -> None:
    """LLM07 — shared checkup/session path uses the same deterministic scorer."""
    resume = TailoredResumeOutput(summary="Engineer.")
    result = compute_score_result(resume, ["Python"])
    assert 0 <= result.ats_score <= 100
    assert sum(axis.max_score for axis in result.axes) == 100


def test_resume_quality_rules_forbid_metric_fabrication() -> None:
    """LLM07 — product rule file matches code-level guardrails."""
    text = QUALITY_RULES.read_text(encoding="utf-8")
    assert "do NOT fabricate" in text.lower() or "not fabricate" in text.lower()
    assert "metrics_needed" in text


def test_phase4_score_module_documents_llm_non_authority() -> None:
    """LLM07 — deterministic engine exists because LLM scores are stochastic."""
    from app.agent import phase4_score

    doc = phase4_score.__doc__ or ""
    assert "deterministic" in doc.lower()
    assert "llm" in doc.lower()
