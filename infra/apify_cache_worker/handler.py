"""Hourly Apify cache worker — fetch top queries and enqueue results."""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib import error, request

import boto3

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

TOP_QUERY_LIMIT = 100


def _postgres_url() -> str:
    url = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("POSTGRES_URL or DATABASE_URL is required")
    # psycopg2 expects postgresql:// not postgresql+asyncpg://
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _fetch_top_queries(limit: int = TOP_QUERY_LIMIT) -> list[dict[str, Any]]:
    import psycopg2

    conn = psycopg2.connect(_postgres_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT query, location, COUNT(*) AS search_count
                FROM job_search_log
                WHERE created_at >= NOW() - INTERVAL '30 days'
                GROUP BY query, location
                ORDER BY search_count DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            return [
                {"query": r[0], "location": r[1], "search_count": r[2]}
                for r in rows
            ]
    finally:
        conn.close()


def _run_apify_scraper(
    query: str,
    location: str | None,
    *,
    token: str,
    actor_id: str,
) -> list[dict[str, Any]]:
    """Start an Apify actor run synchronously and return dataset items."""
    actor_path = actor_id.replace("/", "~")
    input_payload = {
        "queries": [query],
        "location": location or "",
        "maxResults": 10,
    }
    run_url = (
        f"https://api.apify.com/v2/acts/{actor_path}/run-sync-get-dataset-items"
        f"?token={token}&format=json"
    )
    req = request.Request(
        run_url,
        data=json.dumps(input_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=300) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            if isinstance(data, list):
                return data
            return data.get("items") or []
    except error.HTTPError as exc:
        log.error("Apify HTTP error for query=%r: %s", query, exc)
        return []
    except Exception:
        log.exception("Apify scrape failed for query=%r", query)
        return []


def _send_to_sqs(
    queue_url: str,
    query: str,
    location: str | None,
    jobs: list[dict[str, Any]],
    *,
    region: str,
) -> None:
    if not jobs:
        return
    sqs = boto3.client("sqs", region_name=region)
    message = {
        "query": query,
        "location": location,
        "source": "apify",
        "jobs": jobs,
    }
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(message))


def _is_enabled() -> bool:
    return os.environ.get("APIFY_CACHE_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge hourly entrypoint."""
    # Each invocation can start up to TOP_QUERY_LIMIT paid actor runs, so a
    # stray or manual invocation is billable. Refuse unless explicitly enabled.
    if not _is_enabled():
        log.info("apify_cache_worker disabled; set APIFY_CACHE_ENABLED=true to run")
        return {"skipped": True, "reason": "disabled"}

    token = os.environ["APIFY_API_TOKEN"]
    actor_id = os.environ.get("APIFY_ACTOR_ID", "automation-lab/google-jobs-scraper")
    queue_url = os.environ["JOB_CACHE_SQS_URL"]
    region = os.environ.get("AWS_REGION", "us-east-1")

    queries = _fetch_top_queries()
    enqueued = 0
    for row in queries:
        jobs = _run_apify_scraper(
            row["query"],
            row.get("location"),
            token=token,
            actor_id=actor_id,
        )
        if jobs:
            _send_to_sqs(
                queue_url,
                row["query"],
                row.get("location"),
                jobs,
                region=region,
            )
            enqueued += 1

    result = {"queries_processed": len(queries), "batches_enqueued": enqueued}
    log.info("apify_cache_worker complete: %s", result)
    return result
