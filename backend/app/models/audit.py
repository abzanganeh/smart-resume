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


class SuspiciousMetric(BaseModel):
    """A metric in the input resume that cannot be verified from the resume content.

    Phase 2 emits these when it detects round-number percentages, dollar claims
    without a named client, stacked metrics (3+ numbers in one bullet), or numbers
    that appear to be inherited from a prior AI rewrite rather than sourced from
    the candidate's actual experience.

    These are surfaced to the user as a pre-Phase-3 gate — the user either
    confirms them with a source note or replaces them with a verifiable value.
    They do NOT lower the audit score.
    """

    scope: str
    bullet: str
    reason: Literal["round_percentage", "dollar_claim", "stacked_metrics", "no_source"]


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
    unverified_metrics: list[SuspiciousMetric] = []


class AuditLLMOutput(BaseModel):
    """Subset produced by the LLM; keyword_coverage is computed from Phase 1."""

    bullet_issues: list[BulletIssue] = []
    cliches_found: list[str] = []
    irrelevant_sections: list[str] = []
    page_estimate: str = ""
    page_limit_exceeded: bool = False
    contact_issues: list[str] = []
    overall_score: int = 0
    summary: str = ""
    unverified_metrics: list[SuspiciousMetric] = []
