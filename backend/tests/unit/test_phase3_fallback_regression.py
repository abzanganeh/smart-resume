"""Fixture regression: hollow LLM + deterministic fallback + postprocess."""

from __future__ import annotations

import json
from pathlib import Path

from app.agent.phase3_experience_fallback import apply_experience_fallback
from app.agent.phase3_hollow import phase3_total_bullets
from app.agent.phase3_postprocess import postprocess_tailored_output, skills_are_categorized
from app.agent.phase4_score import compute_ats_score
from app.models.resume import ParsedResume
from app.models.rewrite import TailoredResumeOutput

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "phase3" / "hollow_fallback_case.json"


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text())


def test_fixture_fallback_produces_experience_bullets_and_categorized_skills() -> None:
    data = _load_fixture()
    hollow = TailoredResumeOutput.model_validate(data["hollow_llm_output"])
    parsed = ParsedResume.model_validate(data["parsed_resume"])
    must_have = data["must_have_keywords"]

    output = apply_experience_fallback(
        hollow,
        resume_parsed=parsed,
        phase2_output=None,
        prior_output=None,
        must_have_keywords=must_have,
    )
    output = postprocess_tailored_output(output, must_have)

    assert len(output.experience) > 0
    assert phase3_total_bullets(output) > 0
    assert skills_are_categorized(output.skills)


def test_fixture_ats_score_within_baseline_delta() -> None:
    data = _load_fixture()
    hollow = TailoredResumeOutput.model_validate(data["hollow_llm_output"])
    parsed = ParsedResume.model_validate(data["parsed_resume"])
    must_have = data["must_have_keywords"]
    baseline = data["baseline_ats_score"]

    output = apply_experience_fallback(
        hollow,
        resume_parsed=parsed,
        phase2_output=None,
        prior_output=None,
        must_have_keywords=must_have,
    )
    output = postprocess_tailored_output(output, must_have)
    score = compute_ats_score(output, must_have, career_stage="mid")

    assert abs(score.ats_score - baseline) <= 5
