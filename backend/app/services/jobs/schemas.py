"""Pydantic schemas for job search API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class JobResult(BaseModel):
    """Normalized job listing returned by search/match endpoints."""

    id: UUID
    title: str
    company: str
    location: str = ""
    remote: bool = False
    salary_min_usd: int | None = None
    salary_max_usd: int | None = None
    employment_type: str = ""
    posted_date: datetime
    description: str = ""
    apply_url: str = ""
    sources: list[str] = Field(default_factory=list)
    score: float | None = None
    first_seen_at: datetime | None = None


class JobSearchResponse(BaseModel):
    jobs: list[JobResult]
    total: int
    page: int
    page_size: int
    results_may_be_stale: bool = False
    message: str | None = None
    source: str = "hirebase"


class JobSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    location: str | None = Field(default=None, max_length=500)
    filters: dict[str, Any] = Field(default_factory=dict)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)
    expand: bool = False


class JobMatchRequest(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


class SavedSearchCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    query: str = Field(..., min_length=1, max_length=500)
    location: str | None = Field(default=None, max_length=500)
    filters: dict[str, Any] = Field(default_factory=dict)
    alert_frequency: str = Field(default="off")


class SavedSearchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    query: str | None = Field(default=None, min_length=1, max_length=500)
    location: str | None = Field(default=None, max_length=500)
    filters: dict[str, Any] | None = None
    alert_frequency: str | None = None


class SavedSearchOut(BaseModel):
    id: str
    name: str
    query: str
    location: str | None
    filters: dict[str, Any]
    alert_frequency: str
    last_alerted_at: str | None
    created_at: str


class JobPreferencesOut(BaseModel):
    blocked_companies: list[str]
    default_filters: dict[str, Any]


class JobPreferencesUpdate(BaseModel):
    blocked_companies: list[str] | None = None
    default_filters: dict[str, Any] | None = None


__all__ = [
    "JobMatchRequest",
    "JobPreferencesOut",
    "JobPreferencesUpdate",
    "JobResult",
    "JobSearchRequest",
    "JobSearchResponse",
    "SavedSearchCreate",
    "SavedSearchOut",
    "SavedSearchUpdate",
]
