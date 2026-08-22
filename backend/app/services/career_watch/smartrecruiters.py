"""SmartRecruiters public postings API adapter."""

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


def _location_name(location: object) -> str:
    if not isinstance(location, dict):
        return str(location or "")
    parts = [
        str(location.get("city") or ""),
        str(location.get("region") or ""),
        str(location.get("country") or ""),
    ]
    return ", ".join(p for p in parts if p)


def _list_url(slug: str) -> str:
    return (
        f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
        "?limit=100&offset=0"
    )


def _detail_url(slug: str, posting_id: str) -> str:
    return (
        f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}"
    )


def _description_from_detail(detail: dict[str, Any]) -> str:
    sections = detail.get("jobAd") or {}
    if not isinstance(sections, dict):
        return ""
    parts: list[str] = []
    for key in ("jobDescription", "qualifications", "additionalInformation"):
        block = sections.get(key) or {}
        if isinstance(block, dict):
            text = str(block.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def parse_smartrecruiters_payload(
    postings: list[dict[str, Any]],
    *,
    descriptions: dict[str, str] | None = None,
) -> list[ParsedJob]:
    descriptions = descriptions or {}
    parsed: list[ParsedJob] = []
    for item in postings:
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("id") or "")
        if not job_id:
            continue
        apply_url = str(item.get("ref") or item.get("postingUrl") or "")
        parsed.append(
            ParsedJob(
                external_job_id=job_id,
                title=str(item.get("name") or "Untitled"),
                location=_location_name(item.get("location")),
                apply_url=apply_url,
                description_text=descriptions.get(job_id, ""),
                posted_at=_parse_posted_at(str(item.get("releasedDate") or "") or None),
                raw_payload=item,
            )
        )
    return parsed


class SmartRecruitersAdapter:
    async def fetch_jobs(
        self,
        company: WatchedCompany,
        *,
        client: httpx.AsyncClient,
    ) -> list[ParsedJob]:
        slug = company.ats_board_token
        if not slug:
            raise ValueError("smartrecruiters adapter requires ats_board_token")

        payload = await fetch_json(client, _list_url(slug))
        if not isinstance(payload, dict):
            return []
        content = payload.get("content") or []
        if not isinstance(content, list):
            return []

        descriptions: dict[str, str] = {}
        for item in content:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("id") or "")
            if not job_id:
                continue
            try:
                detail = await fetch_json(client, _detail_url(slug, job_id))
            except Exception:  # noqa: BLE001
                continue
            if isinstance(detail, dict):
                descriptions[job_id] = _description_from_detail(detail)

        return parse_smartrecruiters_payload(content, descriptions=descriptions)


__all__ = ["SmartRecruitersAdapter", "parse_smartrecruiters_payload"]
