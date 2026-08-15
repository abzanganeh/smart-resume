"""Unit tests for Phase 3 truthfulness guards (Track B)."""

from __future__ import annotations

from app.agent.phase3_truthfulness import (
    TruthfulnessContext,
    apply_truthfulness_guards,
    enforce_entry_integrity,
    restore_missing_sections,
    validate_bullet_metrics,
)
from app.models.resume import EducationEntry, ExperienceEntry, ParsedResume, ProjectEntry
from app.models.rewrite import TailoredEducationEntry, TailoredExperienceEntry, TailoredResumeOutput
from app.models.session import ApprovedMetric


def test_validate_bullet_metrics_strips_fabricated_number() -> None:
    output = TailoredResumeOutput(
        experience=[
            TailoredExperienceEntry(
                title="QA Engineer",
                company="SecureAuth",
                dates="2020-2024",
                bullets=["Improved validation speed by 30% across the platform."],
            )
        ]
    )
    approved = [ApprovedMetric(scope="SecureAuth", metric="reduced defects by 15%")]
    result = validate_bullet_metrics(output, approved)
    bullet = result.experience[0].bullets[0]
    assert "30%" not in bullet
    assert any("unverified metric" in n.lower() for n in result.rewrite_notes)
    assert len(result.metrics_needed) == 1


def test_validate_bullet_metrics_keeps_scope_correct_metric() -> None:
    output = TailoredResumeOutput(
        experience=[
            TailoredExperienceEntry(
                title="Engineer",
                company="Acme",
                dates="2020-2024",
                bullets=["Reduced defects by 15% through automation."],
            )
        ]
    )
    approved = [ApprovedMetric(scope="Acme", metric="reduced defects by 15%")]
    result = validate_bullet_metrics(output, approved)
    assert "15%" in result.experience[0].bullets[0]
    assert not result.rewrite_notes


def test_validate_bullet_metrics_strips_cross_scope_metric() -> None:
    output = TailoredResumeOutput(
        experience=[
            TailoredExperienceEntry(
                title="Manager",
                company="BR&S",
                dates="2010-2015",
                bullets=["Increased assets by 40% year over year."],
            )
        ]
    )
    approved = [ApprovedMetric(scope="Iran Khodro", metric="program volume grew 40%")]
    result = validate_bullet_metrics(output, approved)
    assert "40%" not in result.experience[0].bullets[0]
    assert any("another scope" in n.lower() for n in result.rewrite_notes)


def test_enforce_entry_integrity_restores_altered_title() -> None:
    parsed = ParsedResume(
        experience=[
            ExperienceEntry(
                title="Senior Software QA Engineer",
                company="SecureAuth",
                dates="2020-2024",
                bullets=["Tested identity platform."],
            )
        ]
    )
    output = TailoredResumeOutput(
        experience=[
            TailoredExperienceEntry(
                title="Senior Software Engineer",
                company="SecureAuth",
                dates="2020-2024",
                bullets=["Tested identity platform."],
            )
        ]
    )
    result = enforce_entry_integrity(output, parsed)
    assert result.experience[0].title == "Senior Software QA Engineer"
    assert any("restored original title" in n.lower() for n in result.rewrite_notes)


def test_enforce_entry_integrity_drops_invented_company() -> None:
    parsed = ParsedResume(
        experience=[
            ExperienceEntry(title="Engineer", company="Acme", dates="2020", bullets=[]),
        ]
    )
    output = TailoredResumeOutput(
        experience=[
            TailoredExperienceEntry(
                title="Director",
                company="Fake Corp",
                dates="2025",
                bullets=["Did things."],
            )
        ]
    )
    result = enforce_entry_integrity(output, parsed)
    assert result.experience == []
    assert any("dropped experience entry" in n.lower() for n in result.rewrite_notes)


def test_restore_missing_sections_re_injects_education_and_projects() -> None:
    parsed = ParsedResume(
        education=[EducationEntry(degree="BS CS", institution="MIT", year="2010")],
        projects=[ProjectEntry(name="Side Project", bullets=["Built API."])],
    )
    output = TailoredResumeOutput(experience=[], education=[], projects=[])
    result = restore_missing_sections(output, parsed)
    assert len(result.education) == 1
    assert result.education[0].institution == "MIT"
    assert len(result.projects) == 1
    assert result.projects[0]["name"] == "Side Project"
    assert any("restored" in n.lower() for n in result.rewrite_notes)


def test_apply_truthfulness_strips_jd_title_from_summary() -> None:
    ctx = TruthfulnessContext(
        jd_job_title="Senior Director, Engineering Quality",
        resume_raw="QA leader with 10 years experience.",
    )
    output = TailoredResumeOutput(
        summary=(
            "Senior Director, Engineering Quality with 10+ years leading QA teams."
        )
    )
    result = apply_truthfulness_guards(output, ctx)
    assert "Senior Director, Engineering Quality" not in result.summary
    assert any("jd job title" in n.lower() for n in result.rewrite_notes)
