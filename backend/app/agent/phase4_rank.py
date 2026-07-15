"""Backend-owned rank labels for Phase 4 ATS guidance.

The LLM never assigns rank — only narrates an already-computed score.
"""

from __future__ import annotations

from typing import Literal

RankLabel = Literal["needs_work", "fair", "good", "great", "excellent"]

_RANK_THRESHOLDS: tuple[tuple[int, RankLabel], ...] = (
    (90, "excellent"),
    (80, "great"),
    (65, "good"),
    (50, "fair"),
    (0, "needs_work"),
)

RANK_DISPLAY: dict[RankLabel, str] = {
    "needs_work": "Needs work",
    "fair": "Fair",
    "good": "Good",
    "great": "Great",
    "excellent": "Excellent",
}


def compute_rank_label(ats_score: int) -> RankLabel:
    """Map a deterministic ATS score to a fixed rank bucket."""
    clamped = max(0, min(100, int(ats_score)))
    for threshold, label in _RANK_THRESHOLDS:
        if clamped >= threshold:
            return label
    return "needs_work"
