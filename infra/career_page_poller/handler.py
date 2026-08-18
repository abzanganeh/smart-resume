"""EventBridge scheduler — enqueue one SQS message per due company."""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

import boto3

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def _postgres_url() -> str:
    url = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("POSTGRES_URL or DATABASE_URL is required")
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _due_company_ids_sql() -> str:
    tier_1 = int(os.environ.get("GLOBAL_POLL_INTERVAL_TIER_1_MINUTES", "15"))
    tier_2 = int(os.environ.get("GLOBAL_POLL_INTERVAL_TIER_2_MINUTES", "30"))
    tier_3 = int(os.environ.get("GLOBAL_POLL_INTERVAL_TIER_3_MINUTES", "45"))
    return f"""
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
        ),
        watch_due AS (
            SELECT wc.id
            FROM watched_companies wc
            JOIN company_intervals ci ON ci.watched_company_id = wc.id
            WHERE wc.is_active = true
              AND (
                wc.last_polled_at IS NULL
                OR wc.last_polled_at <= NOW() - (ci.min_interval || ' minutes')::interval
              )
        ),
        global_due AS (
            SELECT wc.id
            FROM watched_companies wc
            WHERE wc.is_active = true
              AND wc.is_global_seed = true
              AND (
                wc.last_polled_at IS NULL
                OR wc.last_polled_at <= NOW() - (
                    CASE wc.poll_priority_tier
                        WHEN 1 THEN {tier_1}
                        WHEN 3 THEN {tier_3}
                        ELSE {tier_2}
                    END || ' minutes'
                )::interval
              )
        )
        SELECT id FROM (
            SELECT id, 0 AS priority FROM global_due
            UNION
            SELECT id, 1 AS priority FROM watch_due
        ) combined
        ORDER BY priority, id
        LIMIT %s
        """


def build_enqueue_payload(company_id: str) -> str:
    """Serialize one company poll message for SQS."""
    uuid.UUID(company_id)
    return json.dumps({"company_id": company_id})


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    import psycopg2

    queue_url = os.environ.get("CAREER_WATCH_SQS_URL", "")
    if not queue_url:
        raise RuntimeError("CAREER_WATCH_SQS_URL is required")

    batch_limit = int(os.environ.get("CAREER_WATCH_SCHEDULER_BATCH", "200"))
    conn = psycopg2.connect(_postgres_url())
    enqueued = 0
    try:
        with conn.cursor() as cur:
            cur.execute(_due_company_ids_sql(), (batch_limit,))
            company_ids = [str(row[0]) for row in cur.fetchall()]
    finally:
        conn.close()

    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    for company_id in company_ids:
        sqs.send_message(QueueUrl=queue_url, MessageBody=build_enqueue_payload(company_id))
        enqueued += 1

    result = {"enqueued": enqueued}
    log.info("career_page_poller_scheduler_complete %s", result)
    return result
