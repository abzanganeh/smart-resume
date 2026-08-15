"""Rendered tone block for the Phase 3 prompt (Slice A2).

Ensures the JDToneProfile serializes into a stable, minimal instruction block
that Phase 3 can inject without token bloat.
"""

from __future__ import annotations

from app.agent.tone_profile import (
    Formality,
    JDToneProfile,
    ReadingLevel,
    render_tone_profile_block,
)


def test_render_omits_block_for_empty_profile() -> None:
    assert render_tone_profile_block(JDToneProfile()) == ""


def test_render_includes_dominant_verbs_and_register() -> None:
    profile = JDToneProfile(
        formality=Formality.executive,
        industry_register="financial services",
        dominant_verbs=["architect", "orchestrate", "govern"],
        distinctive_phrases=["quality engineering", "enterprise transformation"],
        sentence_length_median=18,
        reading_level=ReadingLevel.dense,
    )

    block = render_tone_profile_block(profile)
    assert "TONE PROFILE" in block
    assert "executive" in block.lower()
    assert "financial services" in block
    assert "architect" in block
    assert "orchestrate" in block
    assert "quality engineering" in block
    assert "dense" in block.lower()


def test_render_caps_and_dedups_lists() -> None:
    profile = JDToneProfile(
        formality=Formality.formal,
        dominant_verbs=["build"] * 5 + ["ship", "own", "deliver"],
        distinctive_phrases=["ml platform"] * 4,
    )
    block = render_tone_profile_block(profile)
    assert block.count("build") == 1
    assert block.count("ml platform") == 1


def test_block_never_leaks_raw_json() -> None:
    profile = JDToneProfile(
        formality=Formality.casual,
        dominant_verbs=["ship"],
    )
    block = render_tone_profile_block(profile)
    assert "{" not in block
    assert "}" not in block
