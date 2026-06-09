from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NewProject(BaseModel):
    """A new project entry to append to the resume projects list."""

    name: str
    description: str | None = None
    bullets: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ResumePatch(BaseModel):
    """A single targeted, apply-able change to one section of the tailored resume."""

    section: Literal[
        "summary", "experience", "skills", "education", "certifications", "projects", "contact"
    ]
    description: str = Field(
        description="Short, plain-English description of what changed and why (shown to user)."
    )

    # ── Contact (header name on exported resume) ───────────────────────────────
    new_name: str | None = Field(
        default=None,
        description="Replacement display name for contact.name. Only set when section='contact'.",
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
    delete_experience: bool = Field(
        default=False,
        description=(
            "When true, remove the entire experience entry matched by company. "
            "Use for deleting manual rows (e.g. Awards). Only set when section='experience'."
        ),
    )

    # ── Certifications ───────────────────────────────────────────────────────
    remove_certifications: list[str] = Field(
        default_factory=list,
        description="Certification or award strings to remove (exact match). section='certifications'.",
    )
    add_certifications: list[str] = Field(
        default_factory=list,
        description="Certification strings to append. section='certifications'.",
    )

    # ── Education ────────────────────────────────────────────────────────────
    institution: str | None = Field(
        default=None,
        description=(
            "School or program name to match — copy EXACTLY from education[].institution. "
            "Only set when section='education'."
        ),
    )
    institution_old: str | None = Field(
        default=None,
        description="Current institution name (for diff display). Optional when section='education'.",
    )
    new_institution: str | None = Field(
        default=None,
        description="Replacement institution name (e.g. shorten 'Interview Kickstart' to 'IK').",
    )
    new_degree: str | None = Field(
        default=None,
        description="Replacement degree text. Only set when section='education'.",
    )
    add_education_bullets: list[str] = Field(
        default_factory=list,
        description="Bullets to append to the matched education entry.",
    )
    education_bullet_old: str | None = Field(
        default=None,
        description="Exact existing education bullet to replace (verbatim).",
    )
    education_bullet_new: str | None = Field(
        default=None,
        description="Replacement education bullet text.",
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
    new_project: NewProject | None = Field(
        default=None,
        description=(
            "A brand-new project to append to the resume. Set name, description (optional), "
            "and bullets. Use ONLY when the project does not already exist in the resume JSON. "
            "Do NOT use project_name/project_bullets_replace_all for a new project."
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
