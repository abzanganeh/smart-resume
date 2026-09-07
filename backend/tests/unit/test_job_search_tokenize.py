"""Unit tests for corpus job-search tokenization."""

from app.services.jobs.job_service import (
    _search_variants_for_term,
    tokenize_job_search_terms,
)


def test_tokenize_keeps_two_letter_role_acronyms() -> None:
    assert tokenize_job_search_terms("Software QA Engineer") == [
        "software",
        "qa",
        "engineer",
    ]


def test_qa_expands_to_quality_and_sdet_aliases() -> None:
    variants = _search_variants_for_term("qa")
    assert "quality engineer" in variants
    assert "sdet" in variants


def test_tokenize_keeps_pm_and_drops_single_char() -> None:
    assert tokenize_job_search_terms("PM role") == ["pm", "role"]
    assert tokenize_job_search_terms("a b c engineer") == ["engineer"]


def test_tokenize_strips_punctuation() -> None:
    assert tokenize_job_search_terms("QA, automation.") == ["qa", "automation"]


def test_tokenize_drops_common_stopwords() -> None:
    assert tokenize_job_search_terms("engineer in remote") == ["engineer", "remote"]
