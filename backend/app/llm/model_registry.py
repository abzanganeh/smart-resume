from __future__ import annotations

from typing import Literal

PipelineStep = Literal[
    "resume_structure",
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

# Step→model pins (verified 2026-08-27, ai.google.dev/gemini-api/docs/pricing).
# One quality bar: tiers differ by volume, not output model.
# Use gemini-3.5-* — gemini-2.5-* returns 404 on many API keys.
STEP_DEFAULTS: dict[PipelineStep, ModelRoute] = {
    "resume_structure": ("gemini", "gemini-3.5-flash-lite"),
    "phase1_keywords": ("gemini", "gemini-3.5-flash-lite"),
    "phase2_audit": ("gemini", "gemini-3.5-flash-lite"),
    "phase3_rewrite": ("gemini", "gemini-3.5-flash"),  # mid flash — paid deliverable
    "phase3_truthfulness": ("gemini", "gemini-3.5-flash-lite"),
    "phase4_qa": ("gemini", "gemini-3.5-flash-lite"),
    "phase4_narrative": ("gemini", "gemini-3.5-flash-lite"),
    "phase4_rank": ("gemini", "gemini-3.5-flash-lite"),
    "polish": ("gemini", "gemini-3.5-flash"),
    "tone_lint": ("gemini", "gemini-3.5-flash-lite"),
    "mechanical_fixes": ("gemini", "gemini-3.5-flash-lite"),
    "cover_letter": ("gemini", "gemini-3.5-flash"),
    "job_fit": ("gemini", "gemini-3.5-flash-lite"),
    "job_title_suggestions": ("gemini", "gemini-3.5-flash-lite"),
    "title_fit_insights": ("gemini", "gemini-3.5-flash-lite"),
    "story": ("gemini", "gemini-3.5-flash"),
    "story_coach": ("gemini", "gemini-3.5-flash"),
    "story_interview": ("gemini", "gemini-3.5-flash"),
    "story_verify": ("gemini", "gemini-3.5-flash-lite"),
    "chat": ("gemini", "gemini-3.5-flash-lite"),
    "company_intel": ("gemini", "gemini-3.5-flash-lite"),
    "checkup": ("gemini", "gemini-3.5-flash-lite"),  # pinned — never settings.LLM_MODEL
}

# Steps that inherit the client from an upstream orchestrator call — visible in
# admin but not editable via tier/global step pins.
INHERITED_CLIENT_STEPS: frozenset[PipelineStep] = frozenset({
    "phase3_truthfulness",
    "phase4_narrative",
    "phase4_rank",
    "tone_lint",
    "title_fit_insights",
})

# Human-readable labels for admin UI (step id → display name).
STEP_LABELS: dict[PipelineStep, str] = {
    "resume_structure": "Resume parse / structure",
    "phase1_keywords": "Phase 1 — keywords",
    "phase2_audit": "Phase 2 — audit",
    "phase3_rewrite": "Phase 3 — rewrite",
    "phase3_truthfulness": "Phase 3 — truthfulness",
    "phase4_qa": "Phase 4 — QA",
    "phase4_narrative": "Phase 4 — narrative",
    "phase4_rank": "Phase 4 — rank",
    "polish": "Polish",
    "tone_lint": "Tone lint",
    "mechanical_fixes": "Mechanical fixes",
    "cover_letter": "Cover letter",
    "job_fit": "Job fit",
    "job_title_suggestions": "Job title suggestions",
    "title_fit_insights": "Title fit insights",
    "story": "Story",
    "story_coach": "Story coach",
    "story_interview": "Story interview",
    "story_verify": "Story verify",
    "chat": "Session chat",
    "company_intel": "Company intel",
    "checkup": "Resume checkup",
}


def all_pipeline_steps() -> list[PipelineStep]:
    """Return canonical step ids in stable order."""
    return list(STEP_DEFAULTS.keys())


def resolve_model(step: PipelineStep, plan_code: str | None = None) -> ModelRoute:
    """Return ``(provider, model)`` for a pipeline step.

    Precedence: tier DB pin → global DB pin → ``STEP_DEFAULTS``.
    """
    if plan_code:
        from app.llm.tier_step_pin_cache import get_tier_step_pin

        tier_pin = get_tier_step_pin(plan_code, step)
        if tier_pin is not None:
            return tier_pin
    from app.llm.step_pin_cache import get_step_pin

    pin = get_step_pin(step)
    if pin is not None:
        return pin
    return STEP_DEFAULTS[step]


def phase_step(phase: int) -> PipelineStep:
    """Map resume pipeline phase number to registry step id."""
    return {
        1: "phase1_keywords",
        2: "phase2_audit",
        3: "phase3_rewrite",
        4: "phase4_qa",
    }[phase]
