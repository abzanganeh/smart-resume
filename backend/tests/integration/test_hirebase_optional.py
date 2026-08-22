"""M19 slice 1 — search works with HIREBASE_API_KEY unset."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import (
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.jobs import JobCache
from tests.integration.test_auth import REGISTER_PAYLOAD
from tests.integration.test_jobs_search import _seed_subscription

pytestmark = pytest.mark.integration


async def _register(client: AsyncClient) -> tuple[str, str]:
    email = f"no-hb-{uuid.uuid4().hex[:8]}@example.com"
    payload = {**REGISTER_PAYLOAD, "email": email}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    return body["access_token"], body["user"]["id"]


async def _seed_corpus_job(db_session: AsyncSession, *, company: str, title: str) -> JobCache:
    now = datetime.now(timezone.utc)
    row = JobCache(
        id=uuid.uuid4(),
        sources=["corpus"],
        external_ids={"greenhouse": "1"},
        title=title,
        company=company,
        company_normalized=company.lower(),
        location="San Francisco, CA",
        remote=False,
        employment_type="",
        posted_date=now,
        description=f"{title} building distributed systems in python.",
        apply_url=f"https://boards.greenhouse.io/{company.lower()}/jobs/1",
        raw_json={},
        cached_at=now,
        expires_at=now + timedelta(days=7),
        dedup_key=f"url:https://boards.greenhouse.io/{company.lower()}/jobs/1",
        first_seen_at=now,
        last_seen_at=now,
        is_active=True,
        apply_url_normalized=f"https://boards.greenhouse.io/{company.lower()}/jobs/1",
        ats_type="greenhouse",
        external_job_id="1",
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest.mark.asyncio
async def test_search_returns_corpus_when_hirebase_key_unset(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Corpus rows and 200 even when expanded provider is not configured."""
    token, user_id = await _register(app_client)
    await _seed_subscription(db_session, user_id)
    await _seed_corpus_job(db_session, company="Stripe", title="Backend Engineer")
    await db_session.commit()

    with (
        patch.object(settings, "HIREBASE_API_KEY", ""),
        patch(
            "app.services.jobs.hirebase_client.search",
            new_callable=AsyncMock,
        ) as mock_search,
        patch.object(settings, "JOB_SEARCH_DB_MIN_RESULTS", 5),
    ):
        res = await app_client.post(
            "/api/jobs/search",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "python backend", "page": 1, "page_size": 20},
        )
        mock_search.assert_not_called()

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "corpus"
    assert body["total"] >= 1
    assert body["results_may_be_stale"] is True
    assert body["message"]
    assert any("Backend" in job["title"] for job in body["jobs"])
