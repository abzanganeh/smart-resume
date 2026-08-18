"""ATS fetch helpers for the Career Watch poll worker (sync urllib)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib import request

USER_AGENT = "TalioCV-CareerWatch/1.0 (+https://taliocv.com)"
FETCH_TIMEOUT = 10


def fetch_json(url: str) -> object:
    req = request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    with request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_greenhouse_jobs(payload: object, *, careers_url: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    jobs = payload.get("jobs") or []
    parsed: list[dict[str, Any]] = []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        external_id = str(item.get("id") or "")
        if not external_id:
            continue
        location = ""
        loc = item.get("location")
        if isinstance(loc, dict):
            location = str(loc.get("name") or "")
        parsed.append(
            {
                "external_job_id": external_id,
                "title": str(item.get("title") or "Untitled"),
                "location": location,
                "apply_url": str(item.get("absolute_url") or careers_url),
                "posted_at": None,
                "raw_payload": item,
            }
        )
    return parsed


def parse_lever_jobs(payload: object, *, careers_url: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    parsed: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        external_id = str(item.get("id") or "")
        if not external_id:
            continue
        categories = item.get("categories") or {}
        location = ""
        if isinstance(categories, dict):
            location = str(categories.get("location") or "")
        parsed.append(
            {
                "external_job_id": external_id,
                "title": str(item.get("text") or "Untitled"),
                "location": location,
                "apply_url": str(item.get("hostedUrl") or careers_url),
                "posted_at": None,
                "raw_payload": item,
            }
        )
    return parsed


def parse_ashby_jobs(payload: object, *, careers_url: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    jobs_raw = payload.get("jobs") or []
    if not isinstance(jobs_raw, list):
        return []
    parsed: list[dict[str, Any]] = []
    for item in jobs_raw:
        if not isinstance(item, dict):
            continue
        external_id = str(item.get("id") or item.get("jobId") or "")
        if not external_id:
            continue
        location = str(item.get("location") or "")
        parsed.append(
            {
                "external_job_id": external_id,
                "title": str(item.get("title") or "Untitled"),
                "location": location,
                "apply_url": str(item.get("jobUrl") or item.get("applyUrl") or careers_url),
                "posted_at": None,
                "raw_payload": item,
            }
        )
    return parsed


def fetch_jobs_for_company(
    *,
    ats_type: str,
    board_token: str,
    careers_url: str,
) -> list[dict[str, Any]]:
    if ats_type == "greenhouse" and board_token:
        payload = fetch_json(
            f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        )
        return parse_greenhouse_jobs(payload, careers_url=careers_url)
    if ats_type == "lever" and board_token:
        payload = fetch_json(f"https://api.lever.co/v0/postings/{board_token}?mode=json")
        return parse_lever_jobs(payload, careers_url=careers_url)
    if ats_type == "ashby" and board_token:
        payload = fetch_json(
            f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
        )
        return parse_ashby_jobs(payload, careers_url=careers_url)
    return []


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
