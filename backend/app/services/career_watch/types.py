"""Shared Career Watch value types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.career_watch import CareerAtsType


@dataclass(frozen=True, slots=True)
class ParsedJob:
    external_job_id: str
    title: str
    location: str
    apply_url: str
    description_text: str
    posted_at: datetime | None
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AtsDetectionResult:
    ats_type: CareerAtsType
    board_token: str | None
    careers_page_url: str
    company_name: str | None = None


__all__ = ["AtsDetectionResult", "ParsedJob"]
