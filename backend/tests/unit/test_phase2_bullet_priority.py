"""Unit tests for Phase 2 bullet issue prioritization."""

from __future__ import annotations

from app.agent.phase2_audit import _prioritize_bullet_issues
from app.models.audit import BulletIssue

pytestmark = __import__("pytest").mark.unit


def test_prioritize_drops_irrelevant_and_caps_count() -> None:
    issues = [
        BulletIssue(
            section="Experience",
            bullet_index=0,
            original="Old hobby bullet",
            issues=["irrelevant"],
            severity="high",
        ),
        BulletIssue(
            section="Experience",
            company="Acme",
            bullet_index=1,
            original="Built APIs with Python",
            issues=["missing_keyword"],
            missing_keywords=["Kubernetes"],
            severity="high",
        ),
        BulletIssue(
            section="Experience",
            company="Acme",
            bullet_index=2,
            original="Led team",
            issues=["no_metric"],
            severity="medium",
        ),
    ]
    result = _prioritize_bullet_issues(issues)
    assert len(result) == 2
    assert result[0].missing_keywords == ["Kubernetes"]
    assert all("irrelevant" not in (i.issues or []) for i in result)


def test_prioritize_keeps_top_ten_by_score() -> None:
    issues = [
        BulletIssue(
            section="Experience",
            bullet_index=i,
            original=f"Bullet {i}",
            issues=["no_metric"],
            severity="low",
        )
        for i in range(15)
    ]
    assert len(_prioritize_bullet_issues(issues)) == 10
