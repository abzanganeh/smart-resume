"""Saved-search alert dispatcher — daily/weekly EventBridge cron."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def _postgres_url() -> str:
    url = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("POSTGRES_URL or DATABASE_URL is required")
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _resolve_schedule(event: dict[str, Any]) -> str:
    """Return ``daily`` or ``weekly`` from the EventBridge payload."""
    detail = event.get("detail") or {}
    schedule = detail.get("schedule") or event.get("schedule")
    if schedule in {"daily", "weekly"}:
        return schedule
    # EventBridge rule name suffix fallback.
    resources = event.get("resources") or []
    for resource in resources:
        if "daily" in resource:
            return "daily"
        if "weekly" in resource:
            return "weekly"
    return "daily"


def _match_jobs(
    conn: Any,
    query: str,
    location: str | None,
    *,
    since: datetime,
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        sql = """
            SELECT id, title, company, location, apply_url, posted_date
            FROM job_cache
            WHERE cached_at >= %s
              AND (title ILIKE %s OR company ILIKE %s OR description ILIKE %s)
        """
        params: list[Any] = [since, f"%{query}%", f"%{query}%", f"%{query}%"]
        if location:
            sql += " AND (location ILIKE %s OR location_city ILIKE %s)"
            params.extend([f"%{location}%", f"%{location}%"])
        sql += " ORDER BY posted_date DESC LIMIT 20"
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [
            {
                "id": str(r[0]),
                "title": r[1],
                "company": r[2],
                "location": r[3],
                "apply_url": r[4],
                "posted_date": r[5].isoformat() if r[5] else None,
            }
            for r in rows
        ]


def _emit_notification(
    conn: Any,
    *,
    user_id: str,
    saved_search_id: str,
    name: str,
    jobs: list[dict[str, Any]],
    channel: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO notifications (
                id, user_id, type, channel, status, payload, created_at
            ) VALUES (
                %s, %s, %s, %s::notification_channel, 'pending'::notification_status,
                %s::jsonb, %s
            )
            """,
            (
                str(uuid.uuid4()),
                user_id,
                "job_alert",
                channel,
                json.dumps(
                    {
                        "saved_search_id": saved_search_id,
                        "name": name,
                        "job_count": len(jobs),
                        "jobs": jobs,
                    }
                ),
                datetime.now(timezone.utc),
            ),
        )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge daily/weekly entrypoint."""
    import psycopg2

    schedule = _resolve_schedule(event)
    now = datetime.now(timezone.utc)
    if schedule == "weekly":
        since = now - timedelta(days=7)
    else:
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)

    conn = psycopg2.connect(_postgres_url())
    alerts_created = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, name, query, location
                FROM saved_search
                WHERE alert_frequency = %s::alert_frequency
                """,
                (schedule,),
            )
            saved_searches = cur.fetchall()

        for ss_id, user_id, name, query, location in saved_searches:
            jobs = _match_jobs(conn, query, location, since=since)
            if not jobs:
                continue
            _emit_notification(
                conn,
                user_id=str(user_id),
                saved_search_id=str(ss_id),
                name=name,
                jobs=jobs,
                channel="in_app",
            )
            _emit_notification(
                conn,
                user_id=str(user_id),
                saved_search_id=str(ss_id),
                name=name,
                jobs=jobs,
                channel="email",
            )
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE saved_search SET last_alerted_at = %s WHERE id = %s",
                    (now, ss_id),
                )
            alerts_created += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    result = {"schedule": schedule, "alerts_created": alerts_created}
    log.info("alert_dispatcher complete: %s", result)
    return result
