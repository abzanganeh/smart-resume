from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class QAItem(BaseModel):
    item: str
    status: Literal["pass", "warn", "fail"]
    note: str = ""


class BlockingIssue(BaseModel):
    category: Literal["keyword", "bullet", "metric", "format", "length", "section"]
    description: str
    suggestion: str
    impact: Literal["high", "medium", "low"]
    fix_effort: Literal["one_click", "user_input", "manual_rewrite"]


class QAOutput(BaseModel):
    checklist: list[QAItem] = Field(default_factory=list)
    overall_status: Literal["pass", "warn", "fail"] = "warn"
    user_action_required: list[str] = Field(default_factory=list)
    # ATS score (Phase 4) — distinct from AuditOutput.overall_score (Phase 2 audit score).
    ats_score: int = Field(default=0, ge=0, le=100)
    blocking_issues: list[BlockingIssue] = Field(default_factory=list)
    score_ceiling: int = Field(default=0, ge=0, le=100)
    quick_wins: list[BlockingIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_ats_guidance_invariants(self) -> "QAOutput":
        impact_rank = {"high": 0, "medium": 1, "low": 2}
        effort_rank = {"one_click": 0, "user_input": 1, "manual_rewrite": 2}

        if self.score_ceiling < self.ats_score:
            raise ValueError("score_ceiling must be >= ats_score")

        sorted_blocking = sorted(
            self.blocking_issues,
            key=lambda issue: (impact_rank[issue.impact], effort_rank[issue.fix_effort]),
        )
        if list(self.blocking_issues) != sorted_blocking:
            raise ValueError(
                "blocking_issues must be ordered by impact desc (high->low), then fix_effort asc "
                "(one_click->user_input->manual_rewrite)"
            )

        blocking_keys = {
            (
                issue.category,
                issue.description,
                issue.suggestion,
                issue.impact,
                issue.fix_effort,
            )
            for issue in self.blocking_issues
        }
        for issue in self.quick_wins:
            if issue.impact != "high" or issue.fix_effort != "one_click":
                raise ValueError(
                    "quick_wins entries must have impact='high' and fix_effort='one_click'"
                )
            key = (
                issue.category,
                issue.description,
                issue.suggestion,
                issue.impact,
                issue.fix_effort,
            )
            if key not in blocking_keys:
                raise ValueError("quick_wins entries must also exist in blocking_issues")

        return self
