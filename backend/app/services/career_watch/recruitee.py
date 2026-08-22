"""Recruitee public offers API adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.models.career_watch import WatchedCompany
from app.services.career_watch.fetch import fetch_json
from app.services.career_watch.types import ParsedJob


def _parse_posted_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_api_url(slug: str) -> str:
    return f"https://{slug}.recruitee.com/api/offers/"


def parse_recruitee_payload(offers: list[dict[str, Any]]) -> list[ParsedJob]:
    parsed: list[ParsedJob] = []
    for item in offers:
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("id") or item.get("slug") or "")
        if not job_id:
            continue
        parsed.append(
            ParsedJob(
                external_job_id=job_id,
                title=str(item.get("title") or "Untitled"),
                location=str(item.get("location") or item.get("city") or ""),
                apply_url=str(item.get("careers_url") or item.get("url") or ""),
                description_text=str(item.get("description") or ""),
                posted_at=_parse_posted_at(str(item.get("published_at") or "") or None),
                raw_payload=item,
            )
        )
    return parsed


class RecruiteeAdapter:
    async def fetch_jobs(
        self,
        company: WatchedCompany,
        *,
        client: httpx.AsyncClient,
    ) -> list[ParsedJob]:
        slug = company.ats_board_token
        if not slug:
            raise ValueError("recruitee adapter requires ats_board_token")

        payload = await fetch_json(client, _build_api_url(slug))
        if not isinstance(payload, dict):
            return []
        offers = payload.get("offers") or []
        if not isinstance(offers, list):
            return []
        return parse_recruitee_payload(offers)


__all__ = ["RecruiteeAdapter", "parse_recruitee_payload"]
