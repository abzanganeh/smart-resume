"""USAJobs official search API (requires API key + User-Agent)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.config import settings
from app.services.career_watch.aggregators.sync import stable_external_id
from app.services.career_watch.fetch import fetch_json
from app.services.career_watch.types import ParsedJob

USAJOBS_SEARCH_URL = "https://data.usajobs.gov/api/search"


def _parse_posted_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _location_descriptor(item: dict[str, Any]) -> str:
    locations = item.get("PositionLocation") or []
    if not isinstance(locations, list) or not locations:
        return ""
    first = locations[0] if isinstance(locations[0], dict) else {}
    city = str(first.get("CityName") or "")
    state = str(first.get("CountrySubDivisionCode") or "")
    country = str(first.get("CountryCode") or "")
    parts = [p for p in (city, state, country) if p]
    return ", ".join(parts)


def parse_usajobs_payload(search_result: dict[str, Any]) -> list[ParsedJob]:
    parsed: list[ParsedJob] = []
    items = search_result.get("SearchResult", {}).get("SearchResultItems") or []
    if not isinstance(items, list):
        return parsed
    for wrapper in items:
        if not isinstance(wrapper, dict):
            continue
        item = wrapper.get("MatchedObjectDescriptor") or {}
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("PositionID") or "")
        title = str(item.get("PositionTitle") or "").strip()
        if not job_id or not title:
            continue
        org = item.get("OrganizationName") or ""
        if isinstance(org, dict):
            company = str(org.get("Name") or org.get("OrganizationName") or "").strip()
        else:
            company = str(org or "").strip()
        apply_url = str(item.get("PositionURI") or item.get("ApplyURI") or "")
        description = str(item.get("UserArea", {}).get("Details", {}).get("MajorDuties") or "")
        if isinstance(item.get("UserArea"), dict):
            details = item["UserArea"].get("Details") or {}
            if isinstance(details, dict) and not description:
                duties = details.get("MajorDuties")
                if isinstance(duties, list):
                    description = "\n".join(str(d) for d in duties)
        parsed.append(
            ParsedJob(
                external_job_id=stable_external_id("usajobs", job_id),
                title=title,
                location=_location_descriptor(item),
                apply_url=apply_url,
                description_text=description,
                posted_at=_parse_posted_at(item.get("PublicationStartDate")),
                raw_payload={**item, "company": company},
            )
        )
    return parsed


async def fetch_usajobs_jobs(*, client: httpx.AsyncClient) -> list[ParsedJob]:
    api_key = settings.USAJOBS_API_KEY.strip()
    user_agent = settings.USAJOBS_USER_AGENT.strip()
    if not api_key or not user_agent:
        return []
    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": user_agent,
        "Authorization-Key": api_key,
    }
    payload = await fetch_json(
        client,
        USAJOBS_SEARCH_URL,
        params={"ResultsPerPage": "100", "Page": "1"},
        headers=headers,
    )
    if not isinstance(payload, dict):
        return []
    return parse_usajobs_payload(payload)


__all__ = ["USAJOBS_SEARCH_URL", "fetch_usajobs_jobs", "parse_usajobs_payload"]
