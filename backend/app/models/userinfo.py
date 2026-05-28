from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, HttpUrl


class UserInfo(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    career_stage: Literal["early_mid", "senior"]
    target_role_type: Literal["ml_engineer", "swe", "data_scientist", "other"]
    certifications: list[str] = []
    is_transitioning_to_ml: bool = False
