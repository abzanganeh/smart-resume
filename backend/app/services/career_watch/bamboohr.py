"""BambooHR public careers list adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.models.career_watch import WatchedCompany
from app.services.career_watch.fetch import CareerWatchFetchError, fetch_json
from app.services.career_watch.types import ParsedJob


def _list_url(slug: str) -> str:
    return f"https://{slug}.bamboohr.com/careers/list"


def _detail_url(slug: str, job_id: str) -> str:
    return f"https://{slug}.bamboohr.com/careers/{job_id}"


def _location_name(location: object) -> str:
    if isinstance(location, dict):
        city = str(location.get("city") or "")
        state = str(location.get("state") or "")
        return ", ".join(p for p in (city, state) if p)
    return str(location or "")


def parse_bamboohr_payload(
    rows: list[dict[str, Any]],
    *,
    descriptions: dict[str, str] | None = None,
) -> list[ParsedJob]:
    descriptions = descriptions or {}
    parsed: list[ParsedJob] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("id") or "")
        if not job_id:
            continue
        parsed.append(
            ParsedJob(
                external_job_id=job_id,
                title=str(item.get("jobOpeningName") or item.get("title") or "Untitled"),
                location=_location_name(item.get("location")),
                apply_url=str(item.get("jobOpeningShareUrl") or ""),
                description_text=descriptions.get(job_id, ""),
                posted_at=None,
                raw_payload=item,
            )
        )
    return parsed


class BambooHrAdapter:
    async def fetch_jobs(
        self,
        company: WatchedCompany,
        *,
        client: httpx.AsyncClient,
    ) -> list[ParsedJob]:
        slug = company.ats_board_token
        if not slug:
            raise ValueError("bamboohr adapter requires ats_board_token")

        payload = await fetch_json(client, _list_url(slug))
        if not isinstance(payload, dict):
            return []
        rows = payload.get("result") or []
        if not isinstance(rows, list):
            return []

        descriptions: dict[str, str] = {}
        for item in rows:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("id") or "")
            if not job_id:
                continue
            try:
                detail = await fetch_json(client, _detail_url(slug, job_id))
            except CareerWatchFetchError:
                continue
            if isinstance(detail, dict):
                result = detail.get("result") or detail
                if isinstance(result, dict):
                    descriptions[job_id] = str(result.get("description") or "")

        return parse_bamboohr_payload(rows, descriptions=descriptions)


__all__ = ["BambooHrAdapter", "parse_bamboohr_payload"]
