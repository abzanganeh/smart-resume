"""We Work Remotely RSS feed."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from xml.etree import ElementTree

import httpx

from app.services.career_watch.aggregators.sync import stable_external_id
from app.services.career_watch.fetch import fetch_text
from app.services.career_watch.types import ParsedJob

WWR_RSS_URL = "https://weworkremotely.com/remote-jobs.rss"

_TITLE_RE = re.compile(r"^(.+?):\s*(.+)$")


def _parse_rss_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _split_title(raw_title: str) -> tuple[str, str]:
    match = _TITLE_RE.match(raw_title.strip())
    if not match:
        return raw_title.strip(), ""
    return match.group(1).strip(), match.group(2).strip()


def parse_wwr_rss(xml_text: str) -> list[ParsedJob]:
    root = ElementTree.fromstring(xml_text)
    parsed: list[ParsedJob] = []
    for item in root.findall(".//item"):
        title_raw = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title_raw or not link:
            continue
        company, title = _split_title(title_raw)
        if not title:
            title = title_raw
        description = (item.findtext("description") or "").strip()
        pub_date = _parse_rss_date(item.findtext("pubDate"))
        parsed.append(
            ParsedJob(
                external_job_id=stable_external_id("weworkremotely", link),
                title=title,
                location="Remote",
                apply_url=link,
                description_text=description,
                posted_at=pub_date,
                raw_payload={
                    "company": company,
                    "remote": True,
                    "rss_title": title_raw,
                },
            )
        )
    return parsed


async def fetch_weworkremotely_jobs(*, client: httpx.AsyncClient) -> list[ParsedJob]:
    xml_text = await fetch_text(client, WWR_RSS_URL)
    return parse_wwr_rss(xml_text)


__all__ = ["WWR_RSS_URL", "fetch_weworkremotely_jobs", "parse_wwr_rss"]
