"""Tests for shared keyword matching."""

from __future__ import annotations

from app.agent.keyword_match import (
    atomize_phrase,
    classify_scoring_tier,
    contains_token,
    string_present,
)


def test_java_does_not_match_javascript() -> None:
    assert contains_token("senior javascript developer", "java") is False


def test_java_matches_standalone() -> None:
    assert contains_token("built services in java and python", "java") is True


def test_atomize_splits_python_and_typescript() -> None:
    atoms = atomize_phrase("Python and TypeScript")
    assert atoms == ["Python", "TypeScript"]


def test_string_present_rejects_absent_skill() -> None:
    assert string_present("Kubernetes", "Built APIs in Python and TypeScript.") is False


def test_string_present_java_not_in_javascript_resume() -> None:
    assert string_present("java", "senior javascript developer") is False


def test_soft_blob_classified_as_context() -> None:
    assert classify_scoring_tier("Strong engineering foundation") == "context"
    assert atomize_phrase("Strong engineering foundation") == []


def test_years_prefix_not_scored() -> None:
    assert atomize_phrase("3+ years building and shipping production software") == []


def test_string_present_finds_split_skills() -> None:
    resume = "Built APIs in Python. Frontend in TypeScript."
    assert string_present("Python", resume)
    assert string_present("TypeScript", resume)
    assert string_present("Python and TypeScript", resume)


def test_abbrev_ml_expansion() -> None:
    assert string_present("ml", "experience with machine learning models")
