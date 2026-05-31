"""Hirebase API client for vector job search (§18.10)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from app.config import settings
from app.services.jobs.circuit_breaker import (
    HirebaseUnavailableError,
    assert_call_allowed,
    record_failure,
    record_probe_failure,
    record_success,
)

log = structlog.get_logger("jobs.hirebase")

HIREBASE_BASE = "https://api.hirebase.org"
VSEARCH_PATH = "/v2/jobs/vsearch"
EMBED_PATH = "/v2/resumes/embed"
DEFAULT_TIMEOUT = 30.0


class HirebaseClientError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.HIREBASE_API_KEY:
        headers["x-api-key"] = settings.HIREBASE_API_KEY
    return headers


def _location_string(locations: list[dict[str, Any]] | None) -> str:
    if not locations:
        return ""
    loc = locations[0]
    bits = [p for p in (loc.get("city"), loc.get("region"), loc.get("country")) if p]
    return ", ".join(bits)


def map_hirebase_job(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Hirebase JSON into ``normalize_apify_record``-compatible dict."""
    locations = raw.get("locations") or []
    salary = raw.get("salary_range") or {}
    return {
        "id": str(raw.get("_id") or raw.get("id") or ""),
        "company": raw.get("company_name") or raw.get("company") or "",
        "title": raw.get("job_title") or raw.get("title") or "",
        "location": _location_string(locations),
        "remote": (raw.get("location_type") or "").lower() == "remote",
        "salary_min": salary.get("min"),
        "salary_max": salary.get("max"),
        "salary_currency": "USD",
        "employment_type": raw.get("job_type") or raw.get("employment_type") or "",
        "posted_date": raw.get("date_posted"),
        "description": raw.get("description") or "",
        "apply_url": raw.get("application_link") or raw.get("apply_url") or "",
        "score": raw.get("score"),
    }


async def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    state = await assert_call_allowed()
    was_probe = state.is_open and state.allow_probe
    url = f"{HIREBASE_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=_headers())
    except httpx.HTTPError as exc:
        if was_probe:
            await record_probe_failure()
        else:
            await record_failure(status_code=None)
        raise HirebaseClientError(str(exc)) from exc

    if resp.status_code >= 400:
        if was_probe:
            await record_probe_failure()
        else:
            await record_failure(status_code=resp.status_code)
        raise HirebaseClientError(
            f"Hirebase error {resp.status_code}: {resp.text[:200]}",
            status_code=resp.status_code,
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        if was_probe:
            await record_probe_failure()
        else:
            await record_failure(status_code=None)
        raise HirebaseClientError("Hirebase returned invalid JSON") from exc

    await record_success()
    return payload


async def embed_resume(resume_text: str) -> str:
    """Upload resume text to Hirebase and return ``artifact_id``."""
    data = await _post(EMBED_PATH, {"resume_text": resume_text})
    artifact_id = data.get("artifact_id") or data.get("id")
    if not artifact_id:
        raise HirebaseClientError("Hirebase embed response missing artifact_id")
    return str(artifact_id)


def _filters_to_hirebase(filters: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if filters.get("remote"):
        out["location_types"] = ["Remote"]
    if min_salary := filters.get("salary_min_usd"):
        out["salary_from"] = min_salary
    if max_salary := filters.get("salary_max_usd"):
        out["salary_to"] = max_salary
    if employment := filters.get("employment_type"):
        out["job_types"] = [employment]
    return out


async def search(
    query: str,
    location: str | None,
    filters: dict[str, Any],
    page: int,
    *,
    page_size: int = 20,
) -> list[dict[str, Any]]:
    """Keyword / natural-language search via ``POST /v2/jobs/vsearch``."""
    payload: dict[str, Any] = {
        "search_type": "summary",
        "query": query,
        "page": page,
        "limit": page_size,
        "top_k": 500,
        "accuracy": 0.3,
    }
    if location:
        parts = [p.strip() for p in location.split(",") if p.strip()]
        loc: dict[str, str] = {}
        if parts:
            loc["city"] = parts[0]
        if len(parts) > 1:
            loc["country"] = parts[-1]
        if loc:
            payload["locations"] = loc
    payload.update(_filters_to_hirebase(filters))

    data = await _post(VSEARCH_PATH, payload)
    return [map_hirebase_job(j) for j in (data.get("jobs") or [])]


async def match_resume(
    artifact_id: str,
    page: int,
    *,
    page_size: int = 20,
) -> list[dict[str, Any]]:
    """Resume match via ``POST /v2/jobs/vsearch`` with ``search_type=resume``."""
    payload = {
        "search_type": "resume",
        "artifact_id": artifact_id,
        "page": page,
        "limit": page_size,
        "top_k": 500,
        "accuracy": 0.3,
    }
    data = await _post(VSEARCH_PATH, payload)
    return [map_hirebase_job(j) for j in (data.get("jobs") or [])]


__all__ = [
    "HirebaseClientError",
    "HirebaseUnavailableError",
    "embed_resume",
    "map_hirebase_job",
    "match_resume",
    "search",
]
