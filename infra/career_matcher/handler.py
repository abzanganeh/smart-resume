"""Career Watch matcher Lambda — keyword filter, alert rows, in-app notifications."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def _postgres_url() -> str:
    url = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("POSTGRES_URL or DATABASE_URL is required")
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _keyword_score(keywords: list[str], title: str, location: str, description: str) -> tuple[float, str]:
    if not keywords:
        return 0.5, "default watch match"
    haystack = f"{title} {location} {description}".lower()
    hits = [kw for kw in keywords if kw.lower() in haystack]
    if not hits:
        return 0.0, ""
    score = min(1.0, len(hits) / max(len(keywords), 1))
    return score, f"matched keywords: {', '.join(hits)}"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    import psycopg2
    from psycopg2.extras import Json

    min_score = float(os.environ.get("CAREER_WATCH_MIN_SCORE", "0.25"))
    batch = int(os.environ.get("CAREER_WATCH_MATCH_BATCH", "200"))
    conn = psycopg2.connect(_postgres_url())
    alerts_created = 0
    notifications_sent = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT uwc.id, uwc.user_id, uwc.watched_company_id, uwc.keywords
                FROM user_watched_companies uwc
                WHERE uwc.is_active = true
                LIMIT %s
                """,
                (batch,),
            )
            watches = cur.fetchall()

            for watch_id, user_id, company_id, keywords in watches:
                kw_list = keywords if isinstance(keywords, list) else []
                cur.execute(
                    """
                    SELECT id, title, location, description_text, apply_url
                    FROM career_job_cache
                    WHERE watched_company_id = %s
                      AND is_open = true
                      AND first_seen_at >= NOW() - INTERVAL '7 days'
                    """,
                    (company_id,),
                )
                for job_id, title, location, description, apply_url in cur.fetchall():
                    score, reason = _keyword_score(
                        kw_list, title or "", location or "", description or ""
                    )
                    if score < min_score:
                        continue
                    alert_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO career_alerts (
                            id, user_id, user_watched_company_id, career_job_cache_id,
                            match_score, match_reason, status, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, 'pending', NOW())
                        ON CONFLICT (user_id, career_job_cache_id) DO NOTHING
                        RETURNING id
                        """,
                        (alert_id, user_id, watch_id, job_id, score, reason),
                    )
                    if cur.fetchone() is None:
                        continue
                    alerts_created += 1

            cur.execute(
                """
                SELECT ca.id, ca.user_id, cjc.title, cjc.apply_url, ca.match_reason
                FROM career_alerts ca
                JOIN career_job_cache cjc ON cjc.id = ca.career_job_cache_id
                WHERE ca.status = 'pending'
                LIMIT %s
                """,
                (batch,),
            )
            pending = cur.fetchall()
            for alert_id, user_id, title, apply_url, reason in pending:
                notif_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO notifications (
                        id, user_id, type, category, channel, title, body, data,
                        scheduled_at, delivery_status, created_at
                    )
                    VALUES (
                        %s, %s, 'career_watch_match', 'job_alerts', 'in_app',
                        %s, %s, %s::jsonb, NOW(), 'pending', NOW()
                    )
                    """,
                    (
                        notif_id,
                        user_id,
                        f"New role: {title}",
                        reason or "A watched company posted a matching role.",
                        Json(
                            {
                                "career_alert_id": str(alert_id),
                                "apply_url": apply_url,
                            }
                        ),
                    ),
                )
                cur.execute(
                    """
                    UPDATE career_alerts
                    SET status = 'sent', notified_at = NOW()
                    WHERE id = %s
                    """,
                    (alert_id,),
                )
                notifications_sent += 1
        conn.commit()
    finally:
        conn.close()
    result = {
        "alerts_created": alerts_created,
        "notifications_sent": notifications_sent,
    }
    log.info("career_matcher_complete %s", result)
    return result
