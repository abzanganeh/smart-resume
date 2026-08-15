"""Phase 3 tone lint (Slice A3).

Deterministic post-process that reads the JD tone profile and the tailored
output, flagging register drift and verb reuse in ``rewrite_notes`` without
mutating bullets.
"""

from __future__ import annotations

from app.agent.tone_lint import annotate_tone_alignment
from app.agent.tone_profile import Formality, JDToneProfile, ReadingLevel
from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput


def _executive_profile() -> JDToneProfile:
    return JDToneProfile(
        formality=Formality.executive,
        industry_register="financial services",
        dominant_verbs=["architect", "orchestrate", "govern", "champion"],
        distinctive_phrases=["quality engineering", "enterprise transformation"],
        sentence_length_median=18,
        reading_level=ReadingLevel.dense,
    )


def _casual_profile() -> JDToneProfile:
    return JDToneProfile(
        formality=Formality.casual,
        industry_register="developer tools / SaaS",
        dominant_verbs=["ship", "build", "fix", "own"],
        distinctive_phrases=["cross-functional team"],
        sentence_length_median=9,
        reading_level=ReadingLevel.plain,
    )


def _output(bullets: list[str]) -> TailoredResumeOutput:
    return TailoredResumeOutput(
        experience=[
            TailoredExperienceEntry(
                title="Director of QA",
                company="Acme",
                dates="2020-2024",
                bullets=bullets,
            )
        ]
    )


def test_lint_no_op_for_neutral_profile() -> None:
    output = _output(["Built X with Y."])
    result = annotate_tone_alignment(output, JDToneProfile())
    assert result == output
    assert result.rewrite_notes == []


def test_lint_flags_low_verb_reuse_for_executive_jd() -> None:
    output = _output(
        [
            "Worked on quality processes across teams.",
            "Helped improve testing coverage in a few areas.",
            "Assisted with governance planning sometimes.",
        ]
    )
    result = annotate_tone_alignment(output, _executive_profile())
    notes = " ".join(result.rewrite_notes).lower()
    assert "tone" in notes
    assert "verb" in notes or "register" in notes


def test_lint_notes_when_executive_bullets_use_casual_verbs() -> None:
    output = _output(
        [
            "Worked on stuff sometimes.",
            "Helped out with quality reviews.",
            "Jumped in to fix bugs when needed.",
        ]
    )
    result = annotate_tone_alignment(output, _executive_profile())
    joined = " ".join(result.rewrite_notes).lower()
    assert any(hint in joined for hint in ("casual verb", "register", "formal"))


def test_lint_passes_when_bullets_reuse_dominant_verbs() -> None:
    output = _output(
        [
            "Architected quality engineering strategy across the enterprise.",
            "Orchestrated compliance transformation with cross-functional partners.",
            "Championed governance framework adoption across business units.",
        ]
    )
    result = annotate_tone_alignment(output, _executive_profile())
    joined = " ".join(result.rewrite_notes).lower()
    # Should NOT flag verb reuse — 3/3 bullets use dominant verbs.
    assert "verb reuse" not in joined or "sufficient" in joined


def test_lint_flags_stiff_language_on_casual_jd() -> None:
    output = _output(
        [
            "Orchestrated enterprise-grade governance frameworks.",
            "Championed rigorous methodological transformation.",
        ]
    )
    result = annotate_tone_alignment(output, _casual_profile())
    joined = " ".join(result.rewrite_notes).lower()
    assert any(hint in joined for hint in ("register", "stiff", "casual", "formal"))


def test_lint_never_mutates_bullets() -> None:
    original_bullets = ["Worked on things.", "Helped teams sometimes."]
    output = _output(list(original_bullets))
    result = annotate_tone_alignment(output, _executive_profile())
    assert result.experience[0].bullets == original_bullets
