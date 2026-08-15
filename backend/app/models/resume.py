from __future__ import annotations

from pydantic import BaseModel


class ContactInfo(BaseModel):
    name: str = ""
    email: str = ""
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    location: str | None = None
    website: str | None = None


class ExperienceEntry(BaseModel):
    title: str = ""
    company: str = ""
    dates: str = ""
    bullets: list[str] = []


class ProjectEntry(BaseModel):
    name: str = ""
    description: str | None = None
    bullets: list[str] = []
    url: str | None = None


class EducationEntry(BaseModel):
    degree: str = ""
    institution: str = ""
    year: str | None = None
    notes: str | None = None


class ParsedResume(BaseModel):
    contact: ContactInfo = ContactInfo()
    summary: str | None = None
    skills: list[str] = []
    experience: list[ExperienceEntry] = []
    projects: list[ProjectEntry] = []
    education: list[EducationEntry] = []
    certifications: list[str] = []
