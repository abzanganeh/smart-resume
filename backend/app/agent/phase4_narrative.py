"""Narrative synthesis layer for Phase 4 ATS guidance (M13 Step 41)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.phase4_rank import RankLabel, compute_rank_label
from app.agent.phase4_score import AxisScore, ResumeQualityResult
from app.llm.base import LLMClient, LLMMessage
from app.llm.structured import complete_structured

_SYSTEM_BASE = (Path(__file__).parent / "prompts" / "system_base.txt").read_text()
_PHASE4_NARRATIVE = (Path(__file__).parent / "prompts" / "phase4_narrative.txt").read_text()

CategorySeverity = Literal["minor", "urgent", "critical"]

NARRATIVE_CATEGORIES: tuple[dict[str, object], ...] = (
    {
        "key": "relevance",
        "label": "Relevance",
        "axis_keys": ("keyword_presence", "keyword_dual_placement"),
    },
    {
        "key": "impact",
        "label": "Impact & Achievements",
        "axis_keys": ("bullet_metrics", "action_verbs"),
    },
    {
        "key": "style",
        "label": "Style & Sections",
        "axis_keys": (
            "section_completeness",
            "contact_completeness",
            "field_completeness",
            "bullet_length",
            "resume_length",
            "weak_phrases",
            "first_person",
            "buzzwords",
        ),
    },
)


class NarrativeCategorySummary(BaseModel):
    category_key: str
    label: str
    severity: CategorySeverity
    issue_count: int = Field(ge=0)
    why_it_matters: str = ""


class NarrativeLLMCategory(BaseModel):
    category_key: str
    why_it_matters: str = ""


class NarrativeLLMOutput(BaseModel):
    headline: str = ""
    category_summaries: list[NarrativeLLMCategory] = Field(default_factory=list)


class Phase4NarrativeResult(BaseModel):
    rank_label: RankLabel
    headline: str
    category_summaries: list[NarrativeCategorySummary] = Field(default_factory=list)


_narrative_cache: dict[str, Phase4NarrativeResult] = {}


def axis_hash(axes: list[AxisScore]) -> str:
    payload = json.dumps(
        [(axis.key, axis.status, round(axis.score, 1)) for axis in axes],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def narrative_cache_key(ats_score: int, axes: list[AxisScore]) -> str:
    return f"{ats_score}:{axis_hash(axes)}"


def _severity_for_axes(axes: list[AxisScore]) -> CategorySeverity:
    if any(axis.status == "fail" for axis in axes):
        return "critical"
    if any(axis.status == "warn" for axis in axes):
        return "urgent"
    return "minor"


def build_category_summaries(score_result: ResumeQualityResult) -> list[NarrativeCategorySummary]:
    by_key = {axis.key: axis for axis in score_result.axes}
    summaries: list[NarrativeCategorySummary] = []
    for category in NARRATIVE_CATEGORIES:
        axis_keys = category["axis_keys"]
        assert isinstance(axis_keys, tuple)
        group_axes = [by_key[key] for key in axis_keys if key in by_key]
        issue_count = sum(len(axis.issues) for axis in group_axes if axis.status != "pass")
        summaries.append(
            NarrativeCategorySummary(
                category_key=str(category["key"]),
                label=str(category["label"]),
                severity=_severity_for_axes(group_axes),
                issue_count=issue_count,
            )
        )
    return summaries


def _merge_llm_narrative(
    base: list[NarrativeCategorySummary],
    llm_output: NarrativeLLMOutput,
) -> list[NarrativeCategorySummary]:
    why_by_key = {
        item.category_key: item.why_it_matters.strip()
        for item in llm_output.category_summaries
        if item.category_key and item.why_it_matters.strip()
    }
    merged: list[NarrativeCategorySummary] = []
    for item in base:
        merged.append(
            item.model_copy(update={"why_it_matters": why_by_key.get(item.category_key, item.why_it_matters)})
        )
    return merged


async def synthesize_phase4_narrative(
    *,
    llm: LLMClient,
    score_result: ResumeQualityResult,
    target_role: str,
    rank_label: RankLabel | None = None,
) -> Phase4NarrativeResult:
    """Generate headline + category copy for a deterministic score snapshot."""
    resolved_rank = rank_label or compute_rank_label(score_result.ats_score)
    cache_key = narrative_cache_key(score_result.ats_score, score_result.axes)
    cached = _narrative_cache.get(cache_key)
    if cached is not None:
        return cached

    base_categories = build_category_summaries(score_result)
    axis_payload = [
        {
            "key": axis.key,
            "label": axis.label,
            "status": axis.status,
            "score": round(axis.score, 1),
            "max": round(axis.max_score, 1),
            "summary": axis.summary,
            "issues": axis.issues[:5],
        }
        for axis in score_result.axes
    ]
    messages = [
        LLMMessage(role="system", content=_SYSTEM_BASE + "\n\n" + _PHASE4_NARRATIVE),
        LLMMessage(
            role="user",
            content=(
                f"TARGET ROLE: {target_role or 'Unknown'}\n"
                f"ATS SCORE: {score_result.ats_score}\n"
                f"RANK LABEL: {resolved_rank}\n\n"
                f"CATEGORY SUMMARIES (severity + issue_count are authoritative — do not change):\n"
                f"{json.dumps([c.model_dump() for c in base_categories], indent=2)}\n\n"
                f"AXIS SUMMARIES:\n{json.dumps(axis_payload, indent=2)}"
            ),
        ),
    ]

    llm_output = await complete_structured(
        llm,
        messages,
        NarrativeLLMOutput,
        max_tokens=2048,
    )
    result = Phase4NarrativeResult(
        rank_label=resolved_rank,
        headline=(llm_output.headline or "").strip(),
        category_summaries=_merge_llm_narrative(base_categories, llm_output),
    )
    _narrative_cache[cache_key] = result
    return result


def clear_narrative_cache_for_tests() -> None:
    _narrative_cache.clear()
