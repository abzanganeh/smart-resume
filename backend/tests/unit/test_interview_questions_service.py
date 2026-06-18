"""Unit tests for interview question bank service."""

from __future__ import annotations

from app.services.questions.service import _load_bank, list_interview_questions


def test_bank_loads_seed_packs() -> None:
    _load_bank.cache_clear()
    bank = _load_bank()
    assert len(bank) >= 200
    assert any(q.domain == "universal" for q in bank)
    assert any(q.domain == "software_engineering" for q in bank)
    assert any(q.domain == "finance" for q in bank)


def test_list_returns_universal_without_domain() -> None:
    questions = list_interview_questions(limit=10)
    assert len(questions) == 10
    assert all(q.domain == "universal" for q in questions)


def test_list_merges_domain_pack() -> None:
    questions = list_interview_questions(domain="software engineering", limit=50)
    domains = {q.domain for q in questions}
    assert "universal" in domains
    assert "software_engineering" in domains
    assert questions[0].domain == "universal"


def test_seed_includes_canonical_answers() -> None:
    _load_bank.cache_clear()
    bank = _load_bank()
    answered = [q for q in bank if q.canonical_answer]
    assert len(answered) >= 200


def test_role_param_preserves_full_merge_set() -> None:
    without_role = list_interview_questions(domain="software_engineering", limit=100)
    with_role = list_interview_questions(
        domain="software_engineering",
        role="distributed systems engineer",
        limit=100,
    )
    assert len(without_role) == len(with_role)
    assert {q.id for q in without_role} == {q.id for q in with_role}
