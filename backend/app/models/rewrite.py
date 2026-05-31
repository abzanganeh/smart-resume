from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetricNeeded(BaseModel):
    section: str
    company: str | None = None
    bullet_index: int
    prompt: str  # question to ask the user, e.g. "What was the business impact?"


class TailoredExperienceEntry(BaseModel):
    title: str = ""
    company: str = ""
    dates: str = ""
    bullets: list[str] = []
    removed_bullets: list[str] = []
    keywords_injected: list[str] = []


class TailoredEducationEntry(BaseModel):
    degree: str = ""
    institution: str = ""
    year: str = ""
    bullets: list[str] = []


# ---------------------------------------------------------------------------
# Master-resume retrieval transparency (IMPLEMENTATION_PLAN §6a).
#
# These fields are emitted on every Phase 3 run so the UI can render
# the "selected vs skipped" panel from SYSTEM_DESIGN_PHASE_2 §18.4.
# They are intentionally permissive ``dict``s with documented shapes
# so we don't tightly couple Phase 3 output to ORM types.
# ---------------------------------------------------------------------------


class TailoredResumeOutput(BaseModel):
    contact: dict = {}
    summary: str = ""
    skills: list[str] = []
    experience: list[TailoredExperienceEntry] = []
    projects: list[dict] = []
    education: list[TailoredEducationEntry] = []
    certifications: list[str] = []
    rewrite_notes: list[str] = []
    metrics_needed: list[MetricNeeded] = []

    # Step 10 — master-resume retrieval trace.  ``selected_chunks`` is a
    # list of ``{chunk_id, section, score, tokens}`` dicts.
    # ``skipped_chunks`` adds a ``reason`` field
    # (``below_threshold | cap_exceeded | budget_exceeded | fallback_used``).
    # ``retrieval_meta`` carries the resolved thresholds, embedding model,
    # total token count, and fallback flags — see
    # :class:`app.services.retrieval.retrieval_service.RetrievalResult.to_trace`.
    selected_chunks: list[dict[str, Any]] = Field(default_factory=list)
    skipped_chunks: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_meta: dict[str, Any] = Field(default_factory=dict)


class ResumeVersion(BaseModel):
    version: int
    snapshot_id: str
    created_at: str
    label: str
    output: TailoredResumeOutput
