"""EventBridge-triggered Career Watch poller — fetch due companies and upsert jobs."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib import error, request

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

USER_AGENT = "FlintResume-CareerWatch/1.0 (+https://flintresume.com)"
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


def _poll_company(conn: Any, company: tuple[Any, ...]) -> int:
    company_id, ats_type, board_token, careers_url = company
    if ats_type != "greenhouse" or not board_token:
        # Non-Greenhouse companies are polled by the ECS backend service.
        return 0

    jobs: list[dict[str, Any]] = []
    jobs = _greenhouse_jobs(board_token)

    upserted = 0
    now = datetime.now(timezone.utc)
    seen: set[str] = set()
    with conn.cursor() as cur:
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
                    %s, '', '', NOW(), NOW(), true, %s::jsonb
                )
                ON CONFLICT (watched_company_id, external_job_id)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    location = EXCLUDED.location,
                    apply_url = EXCLUDED.apply_url,
                    last_seen_at = NOW(),
                    is_open = true
                """,
                (
                    company_id,
                    external_id,
                    title,
                    location,
                    apply_url,
                    json.dumps(item),
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
            UPDATE watched_companies
            SET last_polled_at = %s, poll_fail_count = 0, updated_at = %s
            WHERE id = %s
            """,
            (now, now, company_id),
        )
    return upserted


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    import psycopg2

    interval = int(os.environ.get("CAREER_WATCH_POLL_INTERVAL_MINUTES", "15"))
    limit = int(os.environ.get("CAREER_WATCH_POLL_BATCH", "25"))
    conn = psycopg2.connect(_postgres_url())
    polled = 0
    jobs = 0
    failures = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ats_type::text, ats_board_token, careers_page_url
                FROM watched_companies
                WHERE is_active = true
                  AND ats_type = 'greenhouse'
                  AND ats_board_token IS NOT NULL
                  AND ats_board_token <> ''
                  AND (
                    last_polled_at IS NULL
                    OR last_polled_at <= NOW() - (%s || ' minutes')::interval
                  )
                ORDER BY last_polled_at NULLS FIRST
                LIMIT %s
                """,
                (interval, limit),
            )
            companies = cur.fetchall()
        for company in companies:
            try:
                count = _poll_company(conn, company)
                polled += 1
                jobs += count
                conn.commit()
            except (error.URLError, TimeoutError, psycopg2.Error) as exc:
                failures += 1
                conn.rollback()
                log.warning("poll failed company=%s err=%s", company[0], exc)
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE watched_companies
                        SET poll_fail_count = poll_fail_count + 1, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (company[0],),
                    )
                conn.commit()
    finally:
        conn.close()
    result = {"polled": polled, "jobs_upserted": jobs, "failures": failures}
    log.info("career_page_poller_complete %s", result)
    return result
