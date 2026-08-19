"""Integration tests for job search, circuit breaker, and saved searches."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.jobs import JobCache
from app.models.master_resume import MasterResume
from app.services.jobs import circuit_breaker
from app.services.jobs.cache_writer import normalize_apify_record, upsert_job_cache
from app.services.session_store import redis_set
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


async def _register(client: AsyncClient) -> tuple[str, str]:
    email = f"jobs-{uuid.uuid4().hex[:8]}@example.com"
    payload = {**REGISTER_PAYLOAD, "email": email}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    return body["access_token"], body["user"]["id"]


async def _seed_subscription(db_session: AsyncSession, user_id: str) -> Subscription:
    now = datetime.now(timezone.utc)
    sub = Subscription(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_id),
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        status=SubscriptionStatus.active,
        period_start=now - timedelta(days=1),
        period_end=now + timedelta(days=29),
        cancel_at_period_end=False,
        stripe_customer_id="cus_jobs_test",
        stripe_subscription_id=f"sub_jobs_{uuid.uuid4().hex[:8]}",
        stripe_price_id="price_monthly_test",
        searches_used=0,
    )
    db_session.add(sub)
    await db_session.commit()
    return sub


async def _seed_cache_job(db_session: AsyncSession, *, company: str, title: str) -> JobCache:
    now = datetime.now(timezone.utc)
    record = normalize_apify_record(
        {
            "company": company,
            "title": title,
            "location": "Toronto, Canada",
            "postedDate": now.isoformat(),
            "id": f"cache-{uuid.uuid4().hex[:6]}",
            "description": f"{title} role at {company} building python services.",
        },
        source="apify",
        ttl_seconds=3600,
        now=now,
    )
    return await upsert_job_cache(db_session, record)


async def _open_circuit() -> None:
    until = datetime.now(timezone.utc).timestamp() + 300
    await redis_set(circuit_breaker.OPEN_UNTIL_KEY, str(until))
    await redis_set(circuit_breaker.FAILURES_KEY, "5")


@pytest.mark.asyncio
async def test_circuit_open_serves_stale_cache_without_decrementing_searches(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    sub = await _seed_subscription(db_session, user_id)
    await _seed_cache_job(
        db_session, company="Cached Co", title="Python Developer"
    )
    await db_session.commit()
    await _open_circuit()

    with patch(
        "app.services.jobs.hirebase_client.search",
        new_callable=AsyncMock,
    ) as mock_search:
        res = await app_client.post(
            "/api/jobs/search",
            json={"query": "python developer", "location": "Toronto"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert res.status_code == 200, res.text
    mock_search.assert_not_called()
    body = res.json()
    assert body["results_may_be_stale"] is True
    assert len(body["jobs"]) >= 1
    await db_session.refresh(sub)
    assert sub.searches_used == 0


@pytest.mark.asyncio
async def test_circuit_open_cache_miss_returns_empty_without_quota_decrement(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    sub = await _seed_subscription(db_session, user_id)
    await _open_circuit()

    res = await app_client.post(
        "/api/jobs/search",
        json={"query": "obscure-role-xyz-no-cache", "location": "Antarctica"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["jobs"] == []
    assert body["results_may_be_stale"] is True
    await db_session.refresh(sub)
    assert sub.searches_used == 0


@pytest.mark.asyncio
async def test_saved_search_limit_returns_422_on_eleventh(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    await _seed_subscription(db_session, user_id)
    headers = {"Authorization": f"Bearer {token}"}

    for i in range(10):
        r = await app_client.post(
            "/api/jobs/saved-searches",
            json={
                "name": f"Search {i}",
                "query": f"role {i}",
                "alert_frequency": "off",
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text

    r = await app_client.post(
        "/api/jobs/saved-searches",
        json={"name": "Search 11", "query": "role 11", "alert_frequency": "off"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_five_upstream_500s_open_circuit_and_sixth_uses_cache(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    await _seed_subscription(db_session, user_id)
    await _seed_cache_job(
        db_session, company="Fallback Co", title="Backend Engineer"
    )
    await db_session.commit()

    async def _raise_500(*args, **kwargs):
        await circuit_breaker.record_failure(status_code=500)
        raise circuit_breaker.HirebaseUnavailableError("upstream_500")

    with patch(
        "app.services.jobs.hirebase_client.search",
        side_effect=_raise_500,
    ) as mock_search:
        for _ in range(5):
            res = await app_client.post(
                "/api/jobs/search",
                json={"query": "backend engineer", "location": "Toronto"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200, res.text
            assert res.json()["results_may_be_stale"] is True

        state = await circuit_breaker.get_circuit_state()
        assert state.is_open is True

        sixth = await app_client.post(
            "/api/jobs/search",
            json={"query": "backend engineer", "location": "Toronto"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert sixth.status_code == 200, sixth.text
        body = sixth.json()
        assert body["results_may_be_stale"] is True
        assert len(body["jobs"]) >= 1
        # Once open, the sixth request should short-circuit before the client call.
        assert mock_search.call_count == 5


@pytest.mark.asyncio
async def test_match_without_master_resume_returns_422(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    await _seed_subscription(db_session, user_id)

    res = await app_client.post(
        "/api/jobs/match",
        json={"page": 1, "page_size": 20},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422, res.text
    assert "master resume" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_circuit_open_resume_match_serves_stale_cache(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    await _seed_subscription(db_session, user_id)
    db_session.add(
        MasterResume(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id),
            raw_text="Jane Doe\nSenior Python Engineer with FastAPI and PostgreSQL.",
            hirebase_artifact_id="artifact-test-match",
        )
    )
    await _seed_cache_job(
        db_session, company="Cached Co", title="Python Developer"
    )
    await db_session.commit()
    await _open_circuit()

    with patch(
        "app.services.jobs.hirebase_client.match_resume",
        new_callable=AsyncMock,
    ) as mock_match:
        res = await app_client.post(
            "/api/jobs/match",
            json={"page": 1, "page_size": 20},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert res.status_code == 200, res.text
    mock_match.assert_not_called()
    body = res.json()
    assert body["results_may_be_stale"] is True
    assert len(body["jobs"]) >= 1
