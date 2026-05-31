from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SectionFit(BaseModel):
    section_type: str
    match_score: int = Field(ge=0, le=100)
    matched_items: list[str] = Field(default_factory=list)
    missing_items: list[str] = Field(default_factory=list)


FitLabel = Literal["strong", "good", "partial", "weak"]


class FitAnalysisOutput(BaseModel):
    overall_fit_score: int = Field(ge=0, le=100)
    fit_label: FitLabel
    section_fits: list[SectionFit] = Field(default_factory=list)
    key_gaps: list[str] = Field(default_factory=list)
    key_strengths: list[str] = Field(default_factory=list)
    recommendation: str
    should_apply: bool
    suggested_master_resume_edits: list[str] = Field(default_factory=list)
