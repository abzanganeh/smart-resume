from __future__ import annotations

from pydantic import BaseModel


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


class ResumeVersion(BaseModel):
    version: int
    snapshot_id: str
    created_at: str
    label: str
    output: TailoredResumeOutput
