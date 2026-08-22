"""Personio public XML job feed adapter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

import httpx

from app.models.career_watch import WatchedCompany
from app.services.career_watch.fetch import fetch_text
from app.services.career_watch.types import ParsedJob


def _build_api_url(slug: str) -> str:
    return f"https://{slug}.jobs.personio.com/xml"


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return (node.text or "").strip()


def parse_personio_xml(xml_text: str) -> list[ParsedJob]:
    root = ET.fromstring(xml_text)
    positions = root.findall(".//position")
    if not positions:
        positions = root.findall(".//job")

    parsed: list[ParsedJob] = []
    for item in positions:
        job_id = _text(item.find("id"))
        if not job_id:
            job_id = item.get("id") or ""
        if not job_id:
            continue
        title = _text(item.find("name")) or _text(item.find("title")) or "Untitled"
        location = _text(item.find("office")) or _text(item.find("location"))
        descriptions = item.find("descriptions")
        description_parts: list[str] = []
        if descriptions is not None:
            for child in descriptions:
                text = (child.text or "").strip()
                if text:
                    description_parts.append(text)
        description = _text(item.find("description")) or "\n\n".join(description_parts)
        apply_url = _text(item.find("url")) or _text(item.find("applicationUrl"))
        posted_raw = _text(item.find("createdAt")) or _text(item.find("publishedAt"))
        posted_at = None
        if posted_raw:
            try:
                posted_at = datetime.fromisoformat(posted_raw.replace("Z", "+00:00"))
            except ValueError:
                posted_at = None
        raw_payload: dict[str, Any] = {"id": job_id, "title": title}
        parsed.append(
            ParsedJob(
                external_job_id=str(job_id),
                title=title,
                location=location,
                apply_url=apply_url,
                description_text=description,
                posted_at=posted_at,
                raw_payload=raw_payload,
            )
        )
    return parsed


class PersonioAdapter:
    async def fetch_jobs(
        self,
        company: WatchedCompany,
        *,
        client: httpx.AsyncClient,
    ) -> list[ParsedJob]:
        slug = company.ats_board_token
        if not slug:
            raise ValueError("personio adapter requires ats_board_token")

        xml_text = await fetch_text(
            client,
            _build_api_url(slug),
            accept="application/xml,text/xml,*/*",
        )
        return parse_personio_xml(xml_text)


__all__ = ["PersonioAdapter", "parse_personio_xml"]
