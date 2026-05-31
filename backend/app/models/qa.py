from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
    checklist: list[QAItem] = []
    overall_status: Literal["pass", "warn", "fail"] = "warn"
    user_action_required: list[str] = []
    # ATS score (Phase 4) — distinct from AuditOutput.overall_score (Phase 2 audit score).
    ats_score: int = Field(default=0, ge=0, le=100)
    blocking_issues: list[BlockingIssue] = []
    score_ceiling: int = Field(default=0, ge=0, le=100)
    quick_wins: list[BlockingIssue] = []
