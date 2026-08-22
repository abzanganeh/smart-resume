"""Breezy HR public careers JSON adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.models.career_watch import WatchedCompany
from app.services.career_watch.fetch import CareerWatchFetchError, fetch_json
from app.services.career_watch.types import ParsedJob


def _parse_posted_at(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _list_url(slug: str) -> str:
    return f"https://{slug}.breezy.hr/json"


def _detail_url(slug: str, friendly_id: str) -> str:
    return f"https://{slug}.breezy.hr/json/{friendly_id}"


def _location_name(location: object) -> str:
    if isinstance(location, dict):
        return str(location.get("name") or location.get("city") or "")
    return str(location or "")


def parse_breezy_payload(
    items: list[dict[str, Any]],
    *,
    descriptions: dict[str, str] | None = None,
) -> list[ParsedJob]:
    descriptions = descriptions or {}
    parsed: list[ParsedJob] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("_id") or item.get("friendly_id") or "")
        friendly_id = str(item.get("friendly_id") or job_id)
        if not job_id:
            continue
        parsed.append(
            ParsedJob(
                external_job_id=job_id,
                title=str(item.get("name") or "Untitled"),
                location=_location_name(item.get("location")),
                apply_url=str(item.get("url") or f"https://{friendly_id}.example.com"),
                description_text=descriptions.get(job_id, ""),
                posted_at=_parse_posted_at(item.get("published_date") or item.get("created_date")),
                raw_payload=item,
            )
        )
    return parsed


class BreezyAdapter:
    async def fetch_jobs(
        self,
        company: WatchedCompany,
        *,
        client: httpx.AsyncClient,
    ) -> list[ParsedJob]:
        slug = company.ats_board_token
        if not slug:
            raise ValueError("breezy adapter requires ats_board_token")

        payload = await fetch_json(client, _list_url(slug))
        if not isinstance(payload, list):
            return []

        descriptions: dict[str, str] = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("_id") or "")
            friendly_id = str(item.get("friendly_id") or "")
            if not job_id or not friendly_id:
                continue
            try:
                detail = await fetch_json(client, _detail_url(slug, friendly_id))
            except CareerWatchFetchError:
                continue
            if isinstance(detail, dict):
                descriptions[job_id] = str(detail.get("description") or "")

        return parse_breezy_payload(payload, descriptions=descriptions)


__all__ = ["BreezyAdapter", "parse_breezy_payload"]
