from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ResumePatch(BaseModel):
    """A single targeted, apply-able change to one section of the tailored resume."""

    section: Literal["summary", "experience", "skills", "education", "certifications", "projects"]
    description: str = Field(
        description="Short, plain-English description of what changed and why (shown to user)."
    )

    # ── Summary ──────────────────────────────────────────────────────────────
    new_summary: str | None = Field(
        default=None,
        description="Full replacement text for the summary section. Only set when section='summary'.",
    )

    # ── Skills ───────────────────────────────────────────────────────────────
    add_skills: list[str] = Field(
        default_factory=list,
        description="Skills to append to the skills list. Only set when section='skills'.",
    )
    remove_skills: list[str] = Field(
        default_factory=list,
        description="Skills to remove from the skills list. Only set when section='skills'.",
    )

    # ── Experience bullet ─────────────────────────────────────────────────────
    company: str | None = Field(
        default=None,
        description="Company name (must match exactly). Only set when section='experience'.",
    )
    bullet_old: str | None = Field(
        default=None,
        description="Exact bullet text to find and replace (verbatim). Only set when section='experience'.",
    )
    bullet_new: str | None = Field(
        default=None,
        description="Replacement bullet text. Only set when section='experience'.",
    )


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str = Field(description="Conversational reply shown to the user in the chat bubble.")
    patches: list[ResumePatch] = Field(
        default_factory=list,
        description="Ordered list of changes to apply to the resume. Empty when no change is needed.",
    )
