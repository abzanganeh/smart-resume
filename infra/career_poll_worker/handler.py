"""SQS-triggered Career Watch worker — poll one company per message."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib import error, request

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

USER_AGENT = "TalioCV-CareerWatch/1.0 (+https://taliocv.com)"
FETCH_TIMEOUT = 10


def _postgres_url() -> str:
    url = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("POSTGRES_URL or DATABASE_URL is required")
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _fetch_json(url: str) -> object:
    req = request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    with request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _greenhouse_jobs(board_token: str) -> list[dict[str, Any]]:
    payload = _fetch_json(
        f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    )
    if not isinstance(payload, dict):
        return []
    jobs = payload.get("jobs") or []
    return [j for j in jobs if isinstance(j, dict)]


def _poll_company(conn: Any, company_id: str) -> dict[str, int]:
    import psycopg2

    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, ats_type::text, ats_board_token, careers_page_url
            FROM watched_companies
            WHERE id = %s AND is_active = true
            """,
            (company_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"jobs_upserted": 0, "skipped": 1}

        _cid, name, ats_type, board_token, careers_url = row
        if ats_type != "greenhouse" or not board_token:
            return {"jobs_upserted": 0, "skipped": 1}

        jobs = _greenhouse_jobs(board_token)
        seen: set[str] = set()
        upserted = 0
        for item in jobs:
            external_id = str(item.get("id") or "")
            if not external_id:
                continue
            seen.add(external_id)
            title = str(item.get("title") or "Untitled")
            location = ""
            loc = item.get("location")
            if isinstance(loc, dict):
                location = str(loc.get("name") or "")
            apply_url = str(item.get("absolute_url") or careers_url)
            cur.execute(
                """
                INSERT INTO career_job_cache (
                    id, watched_company_id, external_job_id, title, location,
                    apply_url, description_text, description_hash,
                    first_seen_at, last_seen_at, is_open, raw_payload
                )
                VALUES (
                    gen_random_uuid(), %s, %s, %s, %s,
                    %s, '', '', %s, %s, true, %s::jsonb
                )
                ON CONFLICT (watched_company_id, external_job_id)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    location = EXCLUDED.location,
                    apply_url = EXCLUDED.apply_url,
                    last_seen_at = EXCLUDED.last_seen_at,
                    is_open = true
                """,
                (
                    company_id,
                    external_id,
                    title,
                    location,
                    apply_url,
                    now,
                    now,
                    json.dumps(item),
                ),
            )
            dedup_key = f"url:{apply_url.rstrip('/').lower()}"
            cur.execute(
                """
                INSERT INTO job_cache (
                    id, sources, external_ids, title, company, company_normalized,
                    location, remote, employment_type, posted_date, description,
                    apply_url, raw_json, cached_at, expires_at, dedup_key,
                    first_seen_at, last_seen_at, is_active, apply_url_normalized,
                    ats_type, external_job_id
                )
                VALUES (
                    gen_random_uuid(), '["corpus"]'::jsonb,
                    jsonb_build_object('greenhouse', %s),
                    %s, %s, lower(%s),
                    %s, false, '', %s, '', %s, %s::jsonb,
                    %s, %s + interval '1 day', %s,
                    %s, %s, true, lower(%s), %s, %s
                )
                ON CONFLICT (dedup_key) DO UPDATE SET
                    title = EXCLUDED.title,
                    last_seen_at = EXCLUDED.last_seen_at,
                    is_active = true,
                    expires_at = EXCLUDED.expires_at
                """,
                (
                    external_id,
                    title,
                    name,
                    name,
                    location,
                    now,
                    apply_url,
                    json.dumps(item),
                    now,
                    now,
                    dedup_key,
                    now,
                    now,
                    apply_url,
                    ats_type,
                    external_id,
                ),
            )
            upserted += 1

        cur.execute(
            """
            UPDATE career_job_cache
            SET is_open = false
            WHERE watched_company_id = %s
              AND is_open = true
              AND external_job_id <> ALL(%s)
            """,
            (company_id, list(seen) if seen else [""]),
        )
        cur.execute(
            """
            UPDATE job_cache
            SET is_active = false, last_seen_at = %s
            WHERE company_normalized = lower(%s)
              AND ats_type = %s
              AND is_active = true
              AND external_job_id <> ALL(%s)
            """,
            (now, name, ats_type, list(seen) if seen else [""]),
        )
        cur.execute(
            """
            UPDATE watched_companies
            SET last_polled_at = %s, poll_fail_count = 0, updated_at = %s
            WHERE id = %s
            """,
            (now, now, company_id),
        )
    conn.commit()
    return {"jobs_upserted": upserted}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    import psycopg2

    conn = psycopg2.connect(_postgres_url())
    processed = 0
    failures = 0
    jobs = 0
    try:
        for record in event.get("Records", []):
            try:
                body = json.loads(record.get("body") or "{}")
                company_id = str(body.get("company_id") or "")
                uuid.UUID(company_id)
                result = _poll_company(conn, company_id)
                processed += 1
                jobs += int(result.get("jobs_upserted") or 0)
            except (ValueError, error.URLError, TimeoutError, psycopg2.Error, json.JSONDecodeError) as exc:
                failures += 1
                conn.rollback()
                log.warning("career_poll_worker_failed err=%s", exc)
    finally:
        conn.close()
    summary = {"processed": processed, "jobs_upserted": jobs, "failures": failures}
    log.info("career_poll_worker_complete %s", summary)
    return summary
