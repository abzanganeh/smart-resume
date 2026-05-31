"""Job fit analysis API — shape validation and subscription gate."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    Subscription,
    SubscriptionBillingCycle,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.fit import FitAnalysisOutput, SectionFit
from app.models.user import User
from app.services.master_resume.embedding import set_fake_embedder
from tests.integration.test_auth import REGISTER_PAYLOAD
from tests.retrieval.fake_embedder import deterministic_embed

pytestmark = pytest.mark.integration

SAMPLE_FIT = FitAnalysisOutput(
    overall_fit_score=78,
    fit_label="good",
    section_fits=[
        SectionFit(
            section_type="experience",
            match_score=85,
            matched_items=["Python backend development"],
            missing_items=["Kubernetes at scale"],
        ),
        SectionFit(
            section_type="skills",
            match_score=72,
            matched_items=["FastAPI", "PostgreSQL"],
            missing_items=["Terraform"],
        ),
    ],
    key_gaps=["Kubernetes production experience", "Terraform"],
    key_strengths=["Strong Python/FastAPI background", "PostgreSQL expertise"],
    recommendation=(
        "You are a solid match for this backend role. "
        "Highlight cloud-native experience and consider upskilling on Kubernetes."
    ),
    should_apply=True,
    suggested_master_resume_edits=[
        "Add bullet quantifying API throughput at Acme",
    ],
)

SAMPLE_JD = (
    "Backend Engineer — Python, FastAPI, PostgreSQL, Kubernetes. "
    "5+ years building scalable APIs."
)

SAMPLE_RESUME = (
    "Jane Doe — Backend Engineer\n\n"
    "Experience:\n"
    "- Built Python FastAPI services at Acme Corp serving 2M requests/day.\n"
    "- Designed PostgreSQL schemas and query optimization.\n\n"
    "Skills: Python, FastAPI, PostgreSQL, Redis\n"
)


@pytest.fixture(autouse=True)
def _install_fake_embedder():
    set_fake_embedder(deterministic_embed)
    try:
        yield
    finally:
        set_fake_embedder(None)


async def _register(client: AsyncClient) -> tuple[str, str]:
    email = f"fit-{uuid.uuid4().hex[:8]}@example.com"
    payload = {**REGISTER_PAYLOAD, "email": email}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    return body["access_token"], body["user"]["id"]


async def _seed_subscription(db_session: AsyncSession, user_id: str) -> None:
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
        stripe_customer_id="cus_fit_test",
        stripe_subscription_id=f"sub_fit_{uuid.uuid4().hex[:8]}",
        stripe_price_id="price_monthly_test",
    )
    db_session.add(sub)
    await db_session.commit()


async def _upload_master_resume(client: AsyncClient, token: str) -> None:
    r = await client.post(
        "/api/profile/resume",
        data={"text": SAMPLE_RESUME},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text


async def _parse_sse_events(raw: str) -> list[dict]:
    events: list[dict] = []
    for block in raw.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


async def test_fit_analyze_returns_valid_output_shape(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, user_id = await _register(app_client)
    await _seed_subscription(db_session, user_id)
    await _upload_master_resume(app_client, token)

    async def fake_run(db, *, user_id, jd_text, llm, event_queue):
        await event_queue.put({"event": "progress", "message": "Analyzing…"})
        return SAMPLE_FIT

    monkeypatch.setattr("app.agent.job_fit.run", fake_run)

    res = await app_client.post(
        "/api/fit/analyze",
        data={"jd_text": SAMPLE_JD},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    events = await _parse_sse_events(res.text)
    done = next(e for e in events if e.get("event") == "done")
    output = done["output"]
    FitAnalysisOutput.model_validate(output)
    assert output["overall_fit_score"] == 78
    assert output["fit_label"] == "good"
    assert "analysis_id" in done


async def test_free_user_returns_402(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, _user_id = await _register(app_client)
    await _upload_master_resume(app_client, token)

    async def fake_run(db, *, user_id, jd_text, llm, event_queue):
        return SAMPLE_FIT

    monkeypatch.setattr("app.agent.job_fit.run", fake_run)

    res = await app_client.post(
        "/api/fit/analyze",
        data={"jd_text": SAMPLE_JD},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 402, res.text
    assert res.json()["detail"]["code"] == "subscription_required"
