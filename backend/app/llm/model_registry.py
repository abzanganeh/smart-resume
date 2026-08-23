from __future__ import annotations

from typing import Literal

PipelineStep = Literal[
    "phase1_keywords",
    "phase2_audit",
    "phase3_rewrite",
    "phase3_truthfulness",
    "phase4_qa",
    "phase4_narrative",
    "phase4_rank",
    "polish",
    "tone_lint",
    "mechanical_fixes",
    "cover_letter",
    "job_fit",
    "job_title_suggestions",
    "title_fit_insights",
    "story",
    "story_coach",
    "story_interview",
    "story_verify",
    "chat",
    "company_intel",
    "checkup",
]

ModelRoute = tuple[str, str]

# Step→model pins (verified 2026-08-22, ai.google.dev/gemini-api/docs/pricing).
# One quality bar: tiers differ by volume, not output model.
# Phase 3 stays on gemini-2.5-flash (prior pro-tier default) — not flash-lite.
STEP_DEFAULTS: dict[PipelineStep, ModelRoute] = {
    "phase1_keywords": ("gemini", "gemini-2.5-flash-lite"),
    "phase2_audit": ("gemini", "gemini-2.5-flash-lite"),
    "phase3_rewrite": ("gemini", "gemini-2.5-flash"),  # mid flash — paid deliverable
    "phase3_truthfulness": ("gemini", "gemini-2.5-flash-lite"),
    "phase4_qa": ("gemini", "gemini-2.5-flash-lite"),
    "phase4_narrative": ("gemini", "gemini-2.5-flash-lite"),
    "phase4_rank": ("gemini", "gemini-2.5-flash-lite"),
    "polish": ("gemini", "gemini-2.5-flash"),
    "tone_lint": ("gemini", "gemini-2.5-flash-lite"),
    "mechanical_fixes": ("gemini", "gemini-2.5-flash-lite"),
    "cover_letter": ("gemini", "gemini-2.5-flash"),
    "job_fit": ("gemini", "gemini-2.5-flash-lite"),
    "job_title_suggestions": ("gemini", "gemini-2.5-flash-lite"),
    "title_fit_insights": ("gemini", "gemini-2.5-flash-lite"),
    "story": ("gemini", "gemini-2.5-flash"),
    "story_coach": ("gemini", "gemini-2.5-flash"),
    "story_interview": ("gemini", "gemini-2.5-flash"),
    "story_verify": ("gemini", "gemini-2.5-flash-lite"),
    "chat": ("gemini", "gemini-2.5-flash-lite"),
    "company_intel": ("gemini", "gemini-2.5-flash-lite"),
    "checkup": ("gemini", "gemini-2.5-flash-lite"),  # pinned — never settings.LLM_MODEL
}

# Empty today — reintroducing a premium step override is one map entry.
TIER_STEP_OVERRIDES: dict[str, dict[PipelineStep, ModelRoute]] = {}


def resolve_model(step: PipelineStep, tier: str | None = None) -> ModelRoute:
    """Return ``(provider, model)`` for a pipeline step.

    ``tier`` is reserved for future per-plan overrides; when the override map
    is empty every caller gets the same step default regardless of plan code.
    """
    if tier:
        overrides = TIER_STEP_OVERRIDES.get(tier)
        if overrides and step in overrides:
            return overrides[step]
    return STEP_DEFAULTS[step]


def phase_step(phase: int) -> PipelineStep:
    """Map resume pipeline phase number to registry step id."""
    return {
        1: "phase1_keywords",
        2: "phase2_audit",
        3: "phase3_rewrite",
        4: "phase4_qa",
    }[phase]
