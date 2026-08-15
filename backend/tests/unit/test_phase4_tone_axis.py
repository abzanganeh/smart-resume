"""Phase 4 tone-alignment axis (Slice A4).

Deterministic axis that scores how well the tailored resume mirrors the JD's
vocabulary. Feeds into the total ATS score without breaking the sum-to-100
invariant.
"""

from __future__ import annotations

from app.agent.phase4_score import (
    _W_KEYWORD_PRESENCE,
    _W_TONE_ALIGNMENT,
    compute_ats_score,
)
from app.agent.tone_profile import Formality, JDToneProfile, ReadingLevel
from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput


def _tailored(bullets: list[str], summary: str = "") -> TailoredResumeOutput:
    return TailoredResumeOutput(
        contact={"name": "Jane Doe", "email": "jane@example.com"},
        summary=summary,
        skills=["Leadership: strategy, governance, transformation"],
        experience=[
            TailoredExperienceEntry(
                title="Director of QE",
                company="Acme",
                dates="2020-2024",
                bullets=bullets,
            )
        ],
    )


def _exec_profile() -> JDToneProfile:
    return JDToneProfile(
        formality=Formality.executive,
        industry_register="financial services",
        dominant_verbs=["architect", "orchestrate", "govern", "champion", "establish"],
        distinctive_phrases=["quality engineering", "enterprise transformation"],
        sentence_length_median=18,
        reading_level=ReadingLevel.dense,
    )


def test_axis_weights_still_sum_to_100() -> None:
    """The tone axis must not break the deterministic 0-100 total."""
    resume = _tailored(["Built things."])
    result = compute_ats_score(resume, ["Python"])
    total_max = sum(axis.max_score for axis in result.axes)
    assert round(total_max) == 100


def test_tone_axis_present_in_result() -> None:
    resume = _tailored(["Built things."])
    result = compute_ats_score(resume, ["Python"])
    keys = [axis.key for axis in result.axes]
    assert "tone_alignment" in keys


def test_tone_axis_passes_when_no_profile_supplied() -> None:
    resume = _tailored(["Built things."])
    result = compute_ats_score(resume, ["Python"])
    axis = next(a for a in result.axes if a.key == "tone_alignment")
    assert axis.status == "pass"
    assert axis.score == _W_TONE_ALIGNMENT


def test_tone_axis_scores_higher_when_bullets_reuse_jd_verbs() -> None:
    profile = _exec_profile()
    strong = _tailored(
        [
            "Architected quality engineering strategy across the enterprise.",
            "Orchestrated enterprise transformation with cross-functional partners.",
            "Championed governance framework adoption across business units.",
        ],
        summary="Executive quality engineering leader driving enterprise transformation.",
    )
    weak = _tailored(
        [
            "Wrote code sometimes.",
            "Fixed a few bugs.",
            "Helped teams as needed.",
        ]
    )

    strong_res = compute_ats_score(strong, ["Python"], tone_profile=profile)
    weak_res = compute_ats_score(weak, ["Python"], tone_profile=profile)

    strong_axis = next(a for a in strong_res.axes if a.key == "tone_alignment")
    weak_axis = next(a for a in weak_res.axes if a.key == "tone_alignment")

    assert strong_axis.score > weak_axis.score
    assert strong_axis.status == "pass"
    assert weak_axis.status in {"warn", "fail"}


def test_keyword_presence_weight_reduced_but_axis_still_scores_correctly() -> None:
    """Renormalization moved 5pts from keyword_presence to tone_alignment."""
    assert _W_KEYWORD_PRESENCE == 25
    assert _W_TONE_ALIGNMENT == 5
    assert _W_KEYWORD_PRESENCE + _W_TONE_ALIGNMENT == 30


def test_tone_axis_is_deterministic() -> None:
    profile = _exec_profile()
    resume = _tailored(
        [
            "Architected quality engineering strategy.",
            "Championed enterprise transformation.",
        ]
    )
    first = compute_ats_score(resume, ["Python"], tone_profile=profile)
    second = compute_ats_score(resume, ["Python"], tone_profile=profile)
    first_axis = next(a for a in first.axes if a.key == "tone_alignment")
    second_axis = next(a for a in second.axes if a.key == "tone_alignment")
    assert first_axis.score == second_axis.score
