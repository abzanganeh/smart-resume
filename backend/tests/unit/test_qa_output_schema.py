"""Pydantic validation for Phase 4 QAOutput ATS guidance fields."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.qa import BlockingIssue, QAOutput


def _mock_phase4_payload() -> dict:
    """Representative LLM Phase 4 JSON with all ATS guidance fields."""
    quick_win = {
        "category": "keyword",
        "description": "Missing must-have keyword 'Kubernetes' in Skills and Experience.",
        "suggestion": "Add Kubernetes to Skills and mention container orchestration in the Acme bullet.",
        "impact": "high",
        "fix_effort": "one_click",
    }
    blocking = [
        quick_win,
        {
            "category": "metric",
            "description": "Senior Engineer bullet lacks a quantified outcome.",
            "suggestion": "Add a metric such as 'reduced API latency by 35%'.",
            "impact": "high",
            "fix_effort": "user_input",
        },
        {
            "category": "format",
            "description": "Summary exceeds 60 words.",
            "suggestion": "Trim summary to 2–3 sentences under 60 words.",
            "impact": "low",
            "fix_effort": "manual_rewrite",
        },
    ]
    return {
        "checklist": [
            {"item": "Tailored to one specific JD", "status": "pass", "note": ""},
            {"item": "Top JD keywords in Skills, Experience, Summary", "status": "warn", "note": "Kubernetes missing"},
            {"item": "Bullets start with action verbs + metrics", "status": "warn", "note": "One bullet lacks metric"},
            {"item": "Recruiter-friendly language", "status": "pass", "note": ""},
            {"item": "Only relevant experience included", "status": "pass", "note": ""},
            {"item": "Within page limits", "status": "pass", "note": ""},
            {"item": "Professional contact details", "status": "pass", "note": ""},
            {"item": "ML transition signals visible", "status": "pass", "note": ""},
        ],
        "overall_status": "warn",
        "user_action_required": [],
        "ats_score": 74,
        "blocking_issues": blocking,
        "score_ceiling": 91,
        "quick_wins": [quick_win],
    }


def test_mock_phase4_output_passes_qa_output_schema() -> None:
    output = QAOutput.model_validate(_mock_phase4_payload())

    assert output.ats_score == 74
    assert output.score_ceiling == 91
    assert len(output.blocking_issues) == 3
    assert len(output.quick_wins) == 1
    assert output.quick_wins[0].impact == "high"
    assert output.quick_wins[0].fix_effort == "one_click"
    assert isinstance(output.blocking_issues[0], BlockingIssue)


@pytest.mark.parametrize("field,value", [
    ("ats_score", -1),
    ("ats_score", 101),
    ("score_ceiling", -5),
    ("score_ceiling", 150),
])
def test_ats_score_fields_must_be_in_range(field: str, value: int) -> None:
    payload = _mock_phase4_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        QAOutput.model_validate(payload)


def test_blocking_issue_invalid_category_rejected() -> None:
    payload = _mock_phase4_payload()
    payload["blocking_issues"][0]["category"] = "unknown"
    with pytest.raises(ValidationError):
        QAOutput.model_validate(payload)


def test_score_ceiling_must_not_be_below_ats_score() -> None:
    payload = _mock_phase4_payload()
    payload["score_ceiling"] = payload["ats_score"] - 1
    with pytest.raises(ValidationError):
        QAOutput.model_validate(payload)


def test_blocking_issues_are_auto_sorted_by_impact_then_effort() -> None:
    """Out-of-order LLM output is auto-corrected by the pre-validator,
    not rejected (so we don't waste retries on cosmetic ordering)."""
    payload = _mock_phase4_payload()
    payload["blocking_issues"] = [
        payload["blocking_issues"][2],  # low
        payload["blocking_issues"][0],  # high one_click
        payload["blocking_issues"][1],  # high user_input
    ]

    output = QAOutput.model_validate(payload)

    assert [i.impact for i in output.blocking_issues] == ["high", "high", "low"]
    assert [i.fix_effort for i in output.blocking_issues] == [
        "one_click",
        "user_input",
        "manual_rewrite",
    ]


def test_quick_wins_invalid_entries_are_dropped() -> None:
    """LLM frequently mislabels quick_wins entries (e.g. user_input fix effort).
    Auto-filter rather than fail the whole response."""
    payload = _mock_phase4_payload()
    payload["quick_wins"] = [
        {
            "category": "metric",
            "description": "Manual-only fix that is not a quick win.",
            "suggestion": "Collect hard metrics from the user first.",
            "impact": "high",
            "fix_effort": "user_input",
        }
    ]

    output = QAOutput.model_validate(payload)

    assert output.quick_wins == []


def test_quick_wins_not_in_blocking_issues_are_dropped() -> None:
    """A quick_win must also exist in blocking_issues (single source of truth)."""
    payload = _mock_phase4_payload()
    payload["quick_wins"] = [
        {
            "category": "keyword",
            "description": "Phantom quick win not present in blocking_issues.",
            "suggestion": "Add some keyword.",
            "impact": "high",
            "fix_effort": "one_click",
        }
    ]

    output = QAOutput.model_validate(payload)

    assert output.quick_wins == []
