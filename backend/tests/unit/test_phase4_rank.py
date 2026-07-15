"""Tests for backend-owned Phase 4 rank labels."""

from __future__ import annotations

import pytest

from app.agent.phase4_rank import compute_rank_label


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (95, "excellent"),
        (90, "excellent"),
        (89, "great"),
        (80, "great"),
        (79, "good"),
        (65, "good"),
        (64, "fair"),
        (50, "fair"),
        (49, "needs_work"),
        (0, "needs_work"),
    ],
)
def test_compute_rank_label_thresholds(score: int, expected: str) -> None:
    assert compute_rank_label(score) == expected
