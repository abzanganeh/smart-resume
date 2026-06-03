from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

_IMPACT_RANK = {"high": 0, "medium": 1, "low": 2}
_EFFORT_RANK = {"one_click": 0, "user_input": 1, "manual_rewrite": 2}


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

    @model_validator(mode="before")
    @classmethod
    def _sanitize_ats_guidance(cls, data: Any) -> Any:
        """Auto-correct two common LLM mistakes before strict validation:

        1. `blocking_issues` order — sort by impact desc, then fix_effort asc.
        2. `quick_wins` — drop entries that aren't (impact=high, fix_effort=one_click)
           or that aren't present in `blocking_issues`. This sanitization is
           cheaper than rejecting and re-prompting, and the constraints are
           derived rather than authoritative.
        """
        if not isinstance(data, dict):
            return data

        blocking_raw = data.get("blocking_issues") or []
        if isinstance(blocking_raw, list):
            try:
                blocking_raw = sorted(
                    blocking_raw,
                    key=lambda i: (
                        _IMPACT_RANK.get((i or {}).get("impact"), 99),
                        _EFFORT_RANK.get((i or {}).get("fix_effort"), 99),
                    ),
                )
                data["blocking_issues"] = blocking_raw
            except (TypeError, AttributeError):
                pass

        blocking_keys = {
            (
                (i or {}).get("category"),
                (i or {}).get("description"),
                (i or {}).get("suggestion"),
            )
            for i in (blocking_raw if isinstance(blocking_raw, list) else [])
            if isinstance(i, dict)
        }
        quick_raw = data.get("quick_wins") or []
        if isinstance(quick_raw, list):
            data["quick_wins"] = [
                q
                for q in quick_raw
                if isinstance(q, dict)
                and q.get("impact") == "high"
                and q.get("fix_effort") == "one_click"
                and (q.get("category"), q.get("description"), q.get("suggestion"))
                in blocking_keys
            ]

        return data

    @model_validator(mode="after")
    def _validate_ats_guidance_invariants(self) -> "QAOutput":
        if self.score_ceiling < self.ats_score:
            raise ValueError("score_ceiling must be >= ats_score")
        return self
