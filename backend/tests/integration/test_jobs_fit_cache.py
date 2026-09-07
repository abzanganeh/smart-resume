"""Job-card fit analysis is idempotent per user + job."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fit import FitAnalysisOutput, SectionFit
from app.models.jobs import JobCache
from tests.integration.test_jobs_search import _register, _seed_subscription

pytestmark = pytest.mark.integration

SAMPLE_FIT = FitAnalysisOutput(
    overall_fit_score=72,
    fit_label="good",
    section_fits=[
        SectionFit(
            section_type="experience",
            match_score=75,
            matched_items=["Python"],
            missing_items=["Kubernetes"],
        )
    ],
    key_gaps=["Kubernetes at scale"],
    key_strengths=["Python backend"],
    recommendation="Good match with some gaps.",
    should_apply=True,
    suggested_master_resume_edits=[],
)


async def _seed_job(db_session: AsyncSession) -> JobCache:
    now = datetime.now(timezone.utc)
    job_id = uuid.uuid4()
    row = JobCache(
        id=job_id,
        sources=["corpus"],
        external_ids={"greenhouse": "1"},
        title="QA Engineer",
        company="Acme",
        company_normalized="acme",
        location="Remote",
        remote=True,
        employment_type="full-time",
        posted_date=now,
        description="Software QA engineer with Playwright and API testing experience.",
        apply_url="https://example.com/jobs/1",
        raw_json={},
        cached_at=now,
        expires_at=now + timedelta(days=7),
        dedup_key=f"url:https://example.com/jobs/{job_id}",
        first_seen_at=now,
        last_seen_at=now,
        is_active=True,
        apply_url_normalized="https://example.com/jobs/1",
        ats_type="greenhouse",
        external_job_id="1",
    )
    db_session.add(row)
    await db_session.commit()
    return row


@pytest.mark.asyncio
async def test_job_fit_returns_cached_result_without_rerunning_llm(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    await _seed_subscription(db_session, user_id)
    job = await _seed_job(db_session)

    mock_run = AsyncMock(return_value=SAMPLE_FIT)
    with patch("app.routers.jobs.job_fit_agent.run", mock_run):
        first = await app_client.post(
            f"/api/jobs/{job.id}/fit",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert first.status_code == 200, first.text
        body1 = first.json()
        assert body1["cached"] is False
        analysis_id = body1["analysis_id"]

        second = await app_client.post(
            f"/api/jobs/{job.id}/fit",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert second.status_code == 200, second.text
        body2 = second.json()
        assert body2["cached"] is True
        assert body2["analysis_id"] == analysis_id
        assert body2["result"]["overall_fit_score"] == 72

    assert mock_run.await_count == 1


@pytest.mark.asyncio
async def test_get_job_fit_returns_saved_analysis(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    await _seed_subscription(db_session, user_id)
    job = await _seed_job(db_session)

    missing = await app_client.get(
        f"/api/jobs/{job.id}/fit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "fit_not_found"

    mock_run = AsyncMock(return_value=SAMPLE_FIT)
    with patch("app.routers.jobs.job_fit_agent.run", mock_run):
        created = await app_client.post(
            f"/api/jobs/{job.id}/fit",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert created.status_code == 200, created.text

    loaded = await app_client.get(
        f"/api/jobs/{job.id}/fit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert loaded.status_code == 200, loaded.text
    body = loaded.json()
    assert body["cached"] is True
    assert body["result"]["fit_label"] == "good"
