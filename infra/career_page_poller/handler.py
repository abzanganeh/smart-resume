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


def _due_greenhouse_companies_sql() -> str:
    """SQL selecting Greenhouse companies due for polling by watcher tier intervals."""
    return """
        WITH active_tier_limits AS (
            SELECT DISTINCT ON (plan_code)
                plan_code,
                career_watch_interval_minutes
            FROM tier_limits_config
            WHERE is_active = true
            ORDER BY plan_code, created_at DESC
        ),
        user_overrides AS (
            SELECT DISTINCT ON (user_id)
                user_id,
                payload->>'plan_code' AS plan_code
            FROM admin_user_grants
            WHERE grant_type = 'tier_override'
              AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY user_id, created_at DESC
        ),
        user_subscriptions AS (
            SELECT DISTINCT ON (s.user_id)
                s.user_id,
                pc.code AS plan_code
            FROM subscriptions s
            LEFT JOIN plan_configs pc
              ON pc.stripe_price_id = s.stripe_price_id
             AND pc.is_active = true
            WHERE s.status IN ('trialing', 'active', 'grace', 'cancel_at_period_end')
              AND s.period_start <= NOW()
              AND s.period_end >= NOW()
            ORDER BY s.user_id, s.created_at DESC
        ),
        watcher_plans AS (
            SELECT
                uwc.watched_company_id,
                COALESCE(uo.plan_code, us.plan_code, 'free') AS plan_code
            FROM user_watched_companies uwc
            LEFT JOIN user_overrides uo ON uo.user_id = uwc.user_id
            LEFT JOIN user_subscriptions us ON us.user_id = uwc.user_id
            WHERE uwc.is_active = true
        ),
        company_intervals AS (
            SELECT
                wp.watched_company_id,
                MIN(
                    COALESCE(
                        tl.career_watch_interval_minutes,
                        (SELECT career_watch_interval_minutes
                         FROM active_tier_limits WHERE plan_code = 'free'),
                        30
                    )
                ) AS min_interval
            FROM watcher_plans wp
            LEFT JOIN active_tier_limits tl ON tl.plan_code = wp.plan_code
            GROUP BY wp.watched_company_id
        )
        SELECT wc.id, wc.ats_type::text, wc.ats_board_token, wc.careers_page_url
        FROM watched_companies wc
        JOIN company_intervals ci ON ci.watched_company_id = wc.id
        WHERE wc.is_active = true
          AND wc.ats_type = 'greenhouse'
          AND wc.ats_board_token IS NOT NULL
          AND wc.ats_board_token <> ''
          AND (
            wc.last_polled_at IS NULL
            OR wc.last_polled_at <= NOW() - (ci.min_interval || ' minutes')::interval
          )
        ORDER BY wc.last_polled_at NULLS FIRST
        LIMIT %s
        """


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    import psycopg2

    limit = int(os.environ.get("CAREER_WATCH_POLL_BATCH", "25"))
    conn = psycopg2.connect(_postgres_url())
    polled = 0
    jobs = 0
    failures = 0
    try:
        with conn.cursor() as cur:
            cur.execute(_due_greenhouse_companies_sql(), (limit,))
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
