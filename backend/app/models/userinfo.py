from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class UserInfo(BaseModel):
    name: str = ""
    email: str = ""
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None

    # How far along the candidate is — drives page-length rules
    career_stage: Literal["student", "entry", "mid", "senior", "staff", "executive"] = "mid"

    # Free-text: any role, any industry
    target_role: str = ""

    certifications: list[str] = []

    # True when the candidate is applying outside their primary field.
    # Detected from JD context; only surfaced in the UI for AI/ML jobs.
    is_career_transition: bool = False
