"""SQS consumer — normalize Apify batches and upsert into job_cache."""

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


def _compute_dedup_key(
    company: str, title: str, city: str | None, posted_date: datetime
) -> str:
    city_part = city or ""
    return f"{company.lower()}{title.lower()}{city_part}{posted_date.date().isoformat()}"


def _normalize_location(location_str: str | None) -> tuple[str | None, str | None]:
    if not location_str or not location_str.strip():
        return None, None
    parts = [p.strip() for p in location_str.split(",") if p.strip()]
    if len(parts) == 1:
        return parts[0], None
    if len(parts) == 2:
        return parts[0], parts[1]
    if len(parts) >= 3 and len(parts[1]) == 2:
        return parts[0], parts[-1]
    return parts[0], parts[-1]


def _normalize_record(raw: dict[str, Any], *, ttl_seconds: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    company = str(raw.get("company") or raw.get("companyName") or "")
    title = str(raw.get("title") or raw.get("jobTitle") or "")
    location = str(raw.get("location") or raw.get("locationName") or "")
    city, country = _normalize_location(location)

    posted_raw = raw.get("posted_date") or raw.get("postedDate") or raw.get("datePosted")
    if isinstance(posted_raw, str):
        posted_date = datetime.fromisoformat(posted_raw.replace("Z", "+00:00"))
    elif isinstance(posted_raw, datetime):
        posted_date = posted_raw
    else:
        posted_date = now

    external_id = str(raw.get("id") or raw.get("jobId") or "")
    dedup_key = _compute_dedup_key(company, title, city, posted_date)

    return {
        "sources": json.dumps(["apify"]),
        "external_ids": json.dumps({"apify": external_id} if external_id else {}),
        "title": title,
        "company": company,
        "company_normalized": company.lower(),
        "location": location,
        "location_city": city,
        "location_country": country,
        "remote": bool(raw.get("remote") or raw.get("isRemote")),
        "salary_min_usd": None,
        "salary_max_usd": None,
        "salary_currency_original": None,
        "employment_type": str(raw.get("employment_type") or raw.get("employmentType") or ""),
        "posted_date": posted_date,
        "description": str(raw.get("description") or ""),
        "apply_url": str(raw.get("apply_url") or raw.get("url") or raw.get("link") or ""),
        "raw_json": json.dumps(raw),
        "cached_at": now,
        "expires_at": now + timedelta(seconds=ttl_seconds),
        "dedup_key": dedup_key,
    }


def _upsert_job(conn: Any, record: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, sources, external_ids FROM job_cache WHERE dedup_key = %s",
            (record["dedup_key"],),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                """
                INSERT INTO job_cache (
                    id, sources, external_ids, title, company, company_normalized,
                    location, location_city, location_country, remote,
                    salary_min_usd, salary_max_usd, salary_currency_original,
                    employment_type, posted_date, description, apply_url,
                    raw_json, cached_at, expires_at, dedup_key
                ) VALUES (
                    %s, %s::jsonb, %s::jsonb, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s::jsonb, %s, %s, %s
                )
                """,
                (
                    str(uuid.uuid4()),
                    record["sources"],
                    record["external_ids"],
                    record["title"],
                    record["company"],
                    record["company_normalized"],
                    record["location"],
                    record["location_city"],
                    record["location_country"],
                    record["remote"],
                    record["salary_min_usd"],
                    record["salary_max_usd"],
                    record["salary_currency_original"],
                    record["employment_type"],
                    record["posted_date"],
                    record["description"],
                    record["apply_url"],
                    record["raw_json"],
                    record["cached_at"],
                    record["expires_at"],
                    record["dedup_key"],
                ),
            )
            return

        existing_sources = row[1] or []
        merged_sources = list(existing_sources)
        if "apify" not in merged_sources:
            merged_sources.append("apify")
        existing_ext = row[2] or {}
        incoming_ext = json.loads(record["external_ids"])
        merged_ext = {**existing_ext, **incoming_ext}

        cur.execute(
            """
            UPDATE job_cache SET
                sources = %s::jsonb,
                external_ids = %s::jsonb,
                title = %s,
                company = %s,
                company_normalized = %s,
                location = %s,
                location_city = %s,
                location_country = %s,
                remote = %s,
                employment_type = %s,
                posted_date = %s,
                description = %s,
                apply_url = %s,
                raw_json = %s::jsonb,
                cached_at = %s,
                expires_at = %s
            WHERE dedup_key = %s
            """,
            (
                json.dumps(merged_sources),
                json.dumps(merged_ext),
                record["title"],
                record["company"],
                record["company_normalized"],
                record["location"],
                record["location_city"],
                record["location_country"],
                record["remote"],
                record["employment_type"],
                record["posted_date"],
                record["description"],
                record["apply_url"],
                record["raw_json"],
                record["cached_at"],
                record["expires_at"],
                record["dedup_key"],
            ),
        )


def process_sqs_record(body: str, *, ttl_seconds: int) -> int:
    """Normalize and upsert all jobs in one SQS message body. Returns count written."""
    import psycopg2

    payload = json.loads(body)
    jobs = payload.get("jobs") or []
    if not jobs:
        return 0

    conn = psycopg2.connect(_postgres_url())
    try:
        written = 0
        for raw in jobs:
            record = _normalize_record(raw, ttl_seconds=ttl_seconds)
            _upsert_job(conn, record)
            written += 1
        conn.commit()
        return written
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """SQS Lambda entrypoint."""
    ttl_seconds = int(os.environ.get("JOB_CACHE_TTL_COMMON_SECONDS", "3600"))
    processed = 0
    failed_ids: list[str] = []

    for record in event.get("Records", []):
        message_id = record.get("messageId", "")
        try:
            count = process_sqs_record(record["body"], ttl_seconds=ttl_seconds)
            processed += count
        except Exception:
            log.exception("failed to process SQS message %s", message_id)
            failed_ids.append(message_id)

    # Partial batch failure response for SQS event source mapping.
    batch_failures = [{"itemIdentifier": mid} for mid in failed_ids]
    return {"batchItemFailures": batch_failures, "jobs_written": processed}
