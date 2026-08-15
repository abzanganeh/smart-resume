"""Deterministic JD tone profile extraction (Slice A1).

Tone profile drives Phase 3 wording fidelity + Phase 4 tone alignment axis.
Keep it purely deterministic so the same JD always produces the same profile
and the LLM cannot pressure the score.
"""

from __future__ import annotations

from app.agent.tone_profile import (
    Formality,
    JDToneProfile,
    ReadingLevel,
    extract_tone_profile,
)


_EXEC_FINANCE_JD = """
Senior Director, Engineering Quality

We are seeking a seasoned executive to lead our Quality Engineering
organization. The successful candidate will architect enterprise quality
strategy, orchestrate cross-functional initiatives across regulated financial
services platforms, and champion operational excellence at scale.

Responsibilities:
- Architect and govern quality engineering strategy across the enterprise.
- Orchestrate multi-year transformation initiatives spanning compliance,
  risk, and customer experience domains.
- Champion executive-level stakeholder engagement across business units.
- Establish rigorous governance frameworks and executive scorecards.

Required Qualifications:
- 15+ years of progressive leadership experience in enterprise quality
  engineering.
- Demonstrated track record architecting large-scale transformation programs
  in regulated industries.
- Executive presence and mastery of stakeholder communication at the C-suite.
"""


_CASUAL_SAAS_JD = """
Full-Stack Engineer at a growing startup

We're looking for a developer to help us ship features fast and keep our
users happy. You'll build stuff across the stack, jump on bugs, and work
with a small tight-knit team.

What you'll do:
- Build and ship features across the React frontend and Node.js backend.
- Fix bugs, tune performance, and help debug production issues.
- Pair with designers and PMs to iterate quickly on new ideas.
- Write tests, review PRs, and keep the codebase healthy.

Nice to have:
- Experience with TypeScript and PostgreSQL.
- You've shipped side projects and enjoy learning new tools.
"""


def test_exec_jd_yields_formal_tone_profile() -> None:
    profile = extract_tone_profile(_EXEC_FINANCE_JD)

    assert profile.formality in {Formality.formal, Formality.executive}
    assert profile.reading_level in {ReadingLevel.professional, ReadingLevel.dense}
    assert profile.sentence_length_median >= 8
    assert any(
        verb.lower() in {"architect", "orchestrate", "champion", "establish", "govern"}
        for verb in profile.dominant_verbs
    )


def test_casual_jd_yields_casual_tone_profile() -> None:
    profile = extract_tone_profile(_CASUAL_SAAS_JD)

    assert profile.formality in {Formality.casual, Formality.neutral}
    assert profile.reading_level in {ReadingLevel.plain, ReadingLevel.professional}
    assert any(
        verb.lower() in {"build", "ship", "fix", "pair", "help", "jump"}
        for verb in profile.dominant_verbs
    )


def test_dominant_verbs_are_deduped_and_bounded() -> None:
    profile = extract_tone_profile(_EXEC_FINANCE_JD)
    assert len(profile.dominant_verbs) <= 12
    assert len(profile.dominant_verbs) == len({v.lower() for v in profile.dominant_verbs})


def test_distinctive_phrases_captures_repeated_multiword_terms() -> None:
    profile = extract_tone_profile(_EXEC_FINANCE_JD)
    joined = " ".join(profile.distinctive_phrases).lower()
    assert "quality engineering" in joined
    assert len(profile.distinctive_phrases) <= 8


def test_empty_jd_returns_neutral_profile() -> None:
    profile = extract_tone_profile("")

    assert profile.formality == Formality.neutral
    assert profile.dominant_verbs == []
    assert profile.distinctive_phrases == []
    assert profile.sentence_length_median == 0


def test_tone_profile_is_serializable() -> None:
    profile = extract_tone_profile(_EXEC_FINANCE_JD)
    json_blob = profile.model_dump_json()
    restored = JDToneProfile.model_validate_json(json_blob)
    assert restored.formality == profile.formality
    assert restored.dominant_verbs == profile.dominant_verbs


def test_industry_register_labels_finance_language() -> None:
    profile = extract_tone_profile(_EXEC_FINANCE_JD)
    assert "financial" in profile.industry_register.lower() or "regulated" in profile.industry_register.lower()


def test_industry_register_is_generic_for_generic_jd() -> None:
    generic_jd = "We need a software engineer. Requirements: Python, testing, teamwork. Nice: cloud."
    profile = extract_tone_profile(generic_jd)
    assert profile.industry_register.lower() in {"general", "technology", "software"}
