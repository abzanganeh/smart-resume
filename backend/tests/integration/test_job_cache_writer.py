"""Integration test: SQS consumer acknowledges after successful DB write."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, text

# Lambda handler lives outside the backend package.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "infra" / "job_cache_writer"))

from handler import handler, process_sqs_record  # noqa: E402

from app.models.jobs import JobCache  # noqa: E402

pytestmark = pytest.mark.integration


def _sync_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture()
def sqs_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URL", _sync_database_url())
    monkeypatch.setenv("JOB_CACHE_TTL_COMMON_SECONDS", "3600")


def test_process_sqs_record_writes_job_cache(sqs_env, db_session) -> None:
    body = json.dumps(
        {
            "query": "python developer",
            "location": "Toronto",
            "source": "apify",
            "jobs": [
                {
                    "company": "Widget Inc",
                    "title": "Python Developer",
                    "location": "Toronto, Canada",
                    "postedDate": "2026-05-10T00:00:00Z",
                    "id": "sqs-job-1",
                    "url": "https://example.com/apply",
                }
            ],
        }
    )
    written = process_sqs_record(body, ttl_seconds=3600)
    assert written == 1


@pytest.mark.asyncio
async def test_sqs_handler_returns_no_batch_failures_on_success(
    sqs_env, db_session
) -> None:
    message = {
        "query": "data engineer",
        "jobs": [
            {
                "company": "Data Co",
                "title": "Data Engineer",
                "location": "Remote",
                "postedDate": datetime.now(timezone.utc).isoformat(),
                "id": "sqs-job-2",
            }
        ],
    }
    event = {
        "Records": [
            {
                "messageId": "msg-001",
                "body": json.dumps(message),
            }
        ]
    }

    with patch("handler.process_sqs_record", wraps=process_sqs_record) as wrapped:
        result = handler(event, None)

    assert result["batchItemFailures"] == []
    assert result["jobs_written"] == 1
    wrapped.assert_called_once()

    count = (
        await db_session.execute(
            select(func.count()).select_from(JobCache).where(
                JobCache.company == "Data Co"
            )
        )
    ).scalar_one()
    assert count >= 1

    # Ensure migration tables exist (skipped gracefully if migrations not applied).
    ext = await db_session.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'job_cache'"
        )
    )
    assert ext.scalar() == 1
