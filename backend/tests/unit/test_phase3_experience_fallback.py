"""Unit tests for deterministic Phase 3 experience bullet fallback."""

from __future__ import annotations

import re

from app.agent.phase3_experience_fallback import apply_experience_fallback
from app.agent.phase3_hollow import phase3_total_bullets
from app.models.resume import ExperienceEntry, ParsedResume
from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput


def test_hollow_llm_output_gets_bullets_from_parsed_resume() -> None:
    hollow = TailoredResumeOutput(summary="Strong candidate with relevant skills.")
    parsed = ParsedResume(
        experience=[
            ExperienceEntry(
                title="Software Engineer",
                company="Acme Corp",
                dates="2020-2024",
                bullets=["Built APIs for payments.", "Led migration to Kubernetes."],
            )
        ]
    )
    result = apply_experience_fallback(
        hollow,
        resume_parsed=parsed,
        phase2_output=None,
        prior_output=None,
        must_have_keywords=["Kubernetes"],
    )
    assert len(result.experience) == 1
    assert phase3_total_bullets(result) > 0
    assert any("Kubernetes" in b for b in result.experience[0].bullets)
    assert any("fallback" in n.lower() for n in result.rewrite_notes)


def test_prior_output_bullets_take_precedence_over_parsed() -> None:
    hollow = TailoredResumeOutput()
    parsed = ParsedResume(
        experience=[
            ExperienceEntry(
                company="Acme",
                bullets=["Parsed bullet."],
            )
        ]
    )
    prior = TailoredResumeOutput(
        experience=[
            TailoredExperienceEntry(
                company="Acme",
                title="Senior Engineer",
                bullets=["Prior tailored bullet."],
            )
        ]
    )
    result = apply_experience_fallback(
        hollow,
        resume_parsed=parsed,
        phase2_output=None,
        prior_output=prior,
        must_have_keywords=None,
    )
    assert result.experience[0].bullets == ["Prior tailored bullet."]


def test_fallback_does_not_invent_metrics() -> None:
    hollow = TailoredResumeOutput()
    parsed = ParsedResume(
        experience=[
            ExperienceEntry(
                company="SecureAuth",
                bullets=["Improved test coverage for identity flows."],
            )
        ]
    )
    result = apply_experience_fallback(
        hollow,
        resume_parsed=parsed,
        phase2_output=None,
        prior_output=None,
        must_have_keywords=None,
    )
    bullets_text = " ".join(b for e in result.experience for b in e.bullets)
    assert not re.search(r"\d+%", bullets_text)


def test_empty_parsed_resume_still_records_fallback_note() -> None:
    hollow = TailoredResumeOutput(summary="Summary only.")
    result = apply_experience_fallback(
        hollow,
        resume_parsed=ParsedResume(),
        phase2_output=None,
        prior_output=None,
        must_have_keywords=None,
    )
    assert phase3_total_bullets(result) == 0
    assert any("fallback" in n.lower() for n in result.rewrite_notes)


def test_non_hollow_output_unchanged() -> None:
    output = TailoredResumeOutput(
        experience=[TailoredExperienceEntry(company="Acme", bullets=["Existing bullet."])]
    )
    parsed = ParsedResume(
        experience=[ExperienceEntry(company="Other", bullets=["Should not appear."])]
    )
    result = apply_experience_fallback(
        output,
        resume_parsed=parsed,
        phase2_output=None,
        prior_output=None,
        must_have_keywords=None,
    )
    assert result.experience[0].bullets == ["Existing bullet."]
    assert not result.rewrite_notes
