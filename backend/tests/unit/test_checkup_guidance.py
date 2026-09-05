"""Tests for deterministic checkup guidance."""

from __future__ import annotations

from app.agent.checkup_guidance import build_checkup_guidance, compute_recoverable_ceiling
from app.agent.phase4_score import AxisScore, ResumeQualityResult, compute_ats_score
from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput


def _minimal_result(**kwargs) -> ResumeQualityResult:
    defaults = {
        "ats_score": 50,
        "score_ceiling": 80,
        "axes": [
            AxisScore("keyword_presence", "Keyword coverage", 5, 25, "fail"),
            AxisScore("keyword_dual_placement", "Dual placement", 0, 10, "fail"),
            AxisScore("tone_alignment", "Tone", 3, 5, "warn"),
            AxisScore("bullet_metrics", "Metrics", 10, 15, "warn"),
        ],
        "missing_keywords": ["TypeScript", "Kubernetes"],
        "single_section_keywords": ["Python"],
        "keyword_section_map": {},
    }
    defaults.update(kwargs)
    return ResumeQualityResult(**defaults)


def test_recoverable_ceiling_pinned_for_fixture() -> None:
    result = _minimal_result()
    # 50 + keyword gap 20*0.6 + dual gap 10 + metrics gap 5 = 77, capped at score_ceiling 80
    assert compute_recoverable_ceiling(result) == 80


def test_recoverable_ceiling_at_least_ats_score() -> None:
    result = _minimal_result()
    assert compute_recoverable_ceiling(result) >= result.ats_score
    assert compute_recoverable_ceiling(result) <= result.score_ceiling


def test_build_checkup_guidance_populates_scores() -> None:
    guidance = build_checkup_guidance(_minimal_result())
    assert 0 <= guidance.resume_quality_score <= 100
    assert 0 <= guidance.role_fit_score <= 100
    assert guidance.score_meaning
    assert guidance.tailor_verdict in {"worth_it", "maybe", "skip", "fix_format_only"}


def test_fde_resume_scores_python_typescript_atoms() -> None:
    resume = TailoredResumeOutput(
        contact={"name": "Jane", "email": "j@example.com"},
        summary="Engineer with Python experience.",
        skills=["Python", "TypeScript", "AWS"],
        experience=[
            TailoredExperienceEntry(
                title="Software Engineer",
                company="Acme",
                dates="2020-2024",
                bullets=["Shipped Python APIs and TypeScript admin UI on AWS."],
            )
        ],
        education=[],
        projects=[],
        certifications=[],
    )
    result = compute_ats_score(resume, ["Python", "TypeScript", "Kubernetes"])
    assert "Python" not in result.missing_keywords
    assert "TypeScript" not in result.missing_keywords
    assert "Kubernetes" in result.missing_keywords


def test_java_not_matched_inside_javascript_resume() -> None:
    resume = TailoredResumeOutput(
        contact={"name": "Jane", "email": "j@example.com"},
        summary="Senior JavaScript engineer.",
        skills=["JavaScript", "React"],
        experience=[
            TailoredExperienceEntry(
                title="Frontend Engineer",
                company="Acme",
                dates="2020-2024",
                bullets=["Built React apps in JavaScript."],
            )
        ],
        education=[],
        projects=[],
        certifications=[],
    )
    result = compute_ats_score(resume, ["Java", "JavaScript"])
    assert "Java" in result.missing_keywords
    assert "JavaScript" not in result.missing_keywords
