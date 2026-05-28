from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class BulletIssue(BaseModel):
    section: str
    company: str | None = None
    bullet_index: int
    original: str
    issues: list[Literal["no_action_verb", "no_metric", "cliche", "irrelevant", "missing_keyword"]] = []
    missing_keywords: list[str] = []
    severity: Literal["low", "medium", "high"]


class KeywordCoverage(BaseModel):
    present: list[str] = []
    missing_must_have: list[str] = []
    missing_nice_to_have: list[str] = []


class AuditOutput(BaseModel):
    keyword_coverage: KeywordCoverage = KeywordCoverage()
    bullet_issues: list[BulletIssue] = []
    cliches_found: list[str] = []
    irrelevant_sections: list[str] = []
    page_estimate: str = ""
    page_limit_exceeded: bool = False
    contact_issues: list[str] = []
    overall_score: int = 0
    summary: str = ""
