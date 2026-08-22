"""Ashby public job board API adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.models.career_watch import WatchedCompany
from app.services.career_watch.fetch import fetch_json
from app.services.career_watch.types import ParsedJob


def _build_api_url(board_token: str) -> str:
    return f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"


def _parse_posted_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class AshbyAdapter:
    async def fetch_jobs(
        self,
        company: WatchedCompany,
        *,
        client: httpx.AsyncClient,
    ) -> list[ParsedJob]:
        token = company.ats_board_token
        if not token:
            raise ValueError("ashby adapter requires ats_board_token")

        payload = await fetch_json(client, _build_api_url(token))
        jobs_raw: list[Any] = []
        if isinstance(payload, dict):
            jobs_raw = payload.get("jobs") or []
        if not isinstance(jobs_raw, list):
            return []

        parsed: list[ParsedJob] = []
        for item in jobs_raw:
            if not isinstance(item, dict):
                continue
            if item.get("isListed") is False:
                continue
            job_id = str(item.get("id") or item.get("jobId") or "")
            if not job_id:
                continue
            location = str(item.get("location") or item.get("locationName") or "")
            apply_url = str(item.get("jobUrl") or item.get("applyUrl") or "")
            parsed.append(
                ParsedJob(
                    external_job_id=job_id,
                    title=str(item.get("title") or "Untitled"),
                    location=location,
                    apply_url=apply_url,
                    description_text=str(item.get("descriptionPlain") or ""),
                    posted_at=_parse_posted_at(str(item.get("publishedAt") or "") or None),
                    raw_payload=item,
                )
            )
        return parsed


def parse_ashby_payload(jobs_raw: list[dict[str, Any]]) -> list[ParsedJob]:
    parsed: list[ParsedJob] = []
    for item in jobs_raw:
        job_id = str(item.get("id") or "")
        if not job_id:
            continue
        if item.get("isListed") is False:
            continue
        parsed.append(
            ParsedJob(
                external_job_id=job_id,
                title=str(item.get("title") or "Untitled"),
                location=str(item.get("location") or ""),
                apply_url=str(item.get("jobUrl") or ""),
                description_text=str(item.get("descriptionPlain") or ""),
                posted_at=_parse_posted_at(str(item.get("publishedAt") or "") or None),
                raw_payload=item,
            )
        )
    return parsed


__all__ = ["AshbyAdapter", "parse_ashby_payload"]
