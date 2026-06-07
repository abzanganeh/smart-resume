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

    # ── Experience (bullets, title, dates) ───────────────────────────────────
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
    title_old: str | None = Field(
        default=None,
        description="Current job title (for diff display). Optional when section='experience'.",
    )
    new_title: str | None = Field(
        default=None,
        description="Replacement job title. Only set when section='experience'.",
    )
    dates_old: str | None = Field(
        default=None,
        description="Current date range (for diff display). Optional when section='experience'.",
    )
    new_dates: str | None = Field(
        default=None,
        description="Replacement date range (e.g. '2022 – 2025'). Only set when section='experience'.",
    )

    # ── Projects ─────────────────────────────────────────────────────────────
    remove_projects: list[str] = Field(
        default_factory=list,
        description=(
            "Project names to remove. Copy each name EXACTLY from the resume JSON "
            "'projects[].name' field. Only set when section='projects'."
        ),
    )
    project_name: str | None = Field(
        default=None,
        description=(
            "Project to edit bullets within. Copy name EXACTLY from projects[].name. "
            "Only set when section='projects' and you are editing a bullet."
        ),
    )
    project_bullet_old: str | None = Field(
        default=None,
        description="Exact existing bullet text to replace in the named project. Verbatim copy.",
    )
    project_bullet_new: str | None = Field(
        default=None,
        description="Replacement bullet text for the project. Only set alongside project_bullet_old.",
    )
    project_bullets_replace_all: list[str] = Field(
        default_factory=list,
        description=(
            "Full replacement bullet list for the named project. Use ONLY when replacing "
            "all bullets at once (e.g. user provides a complete rewrite). "
            "project_bullet_old/new takes priority when both are set."
        ),
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
