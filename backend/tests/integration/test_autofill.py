"""Integration tests for autofill payload endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_description import JobDescription
from app.models.rewrite import TailoredResumeOutput
from app.services.session_store import create_session, update_session
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


async def _register(client: AsyncClient, suffix: str = "") -> tuple[str, str]:
    email = f"autofill-{suffix or uuid.uuid4().hex[:6]}@example.com"
    payload = {**REGISTER_PAYLOAD, "email": email}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["access_token"], r.json()["user"]["id"]


@pytest.mark.asyncio
async def test_autofill_payload_requires_tailored_session(app_client: AsyncClient) -> None:
    token, _ = await _register(app_client, "409")

    save_r = await app_client.post(
        "/api/job-descriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "url": "https://boards.greenhouse.io/acme/jobs/123",
            "title": "Engineer",
            "company": "Acme",
            "text": "Build distributed systems with Rust and Kafka for this senior role opening.",
            "source": "extension",
        },
    )
    assert save_r.status_code == 200
    jd_id = save_r.json()["jd_id"]

    payload_r = await app_client.get(
        f"/api/job-descriptions/{jd_id}/autofill-payload",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert payload_r.status_code == 409
    assert payload_r.json()["detail"]["code"] == "resume_not_tailored_yet"


@pytest.mark.asyncio
async def test_autofill_payload_returns_greenhouse_fields(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client, "ok")

    save_r = await app_client.post(
        "/api/job-descriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "url": "https://boards.greenhouse.io/acme/jobs/123",
            "title": "Senior Engineer",
            "company": "Acme",
            "text": "Build distributed systems with Rust and Kafka for this senior role opening.",
            "source": "extension",
        },
    )
    jd_id = save_r.json()["jd_id"]

    session = await create_session()
    session.user_id = user_id
    session.phase3_output = TailoredResumeOutput(
        contact={
            "name": "Alex Rivera",
            "email": "alex@example.com",
            "phone": "555-0100",
            "linkedin": "https://www.linkedin.com/in/alex",
        },
        summary="Tailored resume summary.",
    )
    await update_session(session)

    row = (
        await db_session.execute(select(JobDescription).where(JobDescription.id == uuid.UUID(jd_id)))
    ).scalar_one()
    row.session_id = session.session_id
    await db_session.commit()

    payload_r = await app_client.get(
        f"/api/job-descriptions/{jd_id}/autofill-payload",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert payload_r.status_code == 200, payload_r.text
    body = payload_r.json()
    assert body["platform"] == "greenhouse"
    keys = {field["key"] for field in body["fields"]}
    assert "email" in keys
    assert "resume" in keys
    assert all("summary" not in field["value"].lower() for field in body["fields"])


@pytest.mark.asyncio
async def test_autofill_payload_returns_lever_heuristic_fields(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client, "lever")

    save_r = await app_client.post(
        "/api/job-descriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "url": "https://jobs.lever.co/acme/abc-123",
            "title": "Staff Engineer",
            "company": "Acme",
            "text": "Build platform APIs with Go and Kubernetes for our infrastructure team.",
            "source": "extension",
        },
    )
    jd_id = save_r.json()["jd_id"]

    session = await create_session()
    session.user_id = user_id
    session.phase3_output = TailoredResumeOutput(
        contact={"name": "Alex Rivera", "email": "alex@example.com"},
        summary="Tailored resume summary.",
    )
    await update_session(session)

    row = (
        await db_session.execute(select(JobDescription).where(JobDescription.id == uuid.UUID(jd_id)))
    ).scalar_one()
    row.session_id = session.session_id
    await db_session.commit()

    payload_r = await app_client.get(
        f"/api/job-descriptions/{jd_id}/autofill-payload",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert payload_r.status_code == 200, payload_r.text
    body = payload_r.json()
    assert body["platform"] == "lever"
    assert all(field["selector"] == "" for field in body["fields"])
    email = next(field for field in body["fields"] if field["key"] == "email")
    assert email["value"] == "alex@example.com"


@pytest.mark.asyncio
async def test_recent_tailored_sessions_lists_only_completed_tailoring(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client, "recent")

    save_r = await app_client.post(
        "/api/job-descriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "url": "https://boards.greenhouse.io/acme/jobs/456",
            "title": "Platform Engineer",
            "company": "Beta Co",
            "text": "Own platform reliability and observability for customer-facing APIs and data.",
            "source": "extension",
        },
    )
    jd_id = save_r.json()["jd_id"]

    session = await create_session()
    session.user_id = user_id
    session.phase3_output = TailoredResumeOutput(
        contact={"name": "Sam", "email": "sam@example.com"},
        summary="Tailored.",
    )
    await update_session(session)

    row = (
        await db_session.execute(select(JobDescription).where(JobDescription.id == uuid.UUID(jd_id)))
    ).scalar_one()
    row.session_id = session.session_id
    await db_session.commit()

    list_r = await app_client.get(
        "/api/job-descriptions/recent-tailored",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_r.status_code == 200, list_r.text
    sessions = list_r.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["jd_id"] == jd_id
    assert sessions[0]["company"] == "Beta Co"
    assert sessions[0]["url_host"] == "boards.greenhouse.io"


@pytest.mark.asyncio
async def test_autofill_payload_isolation_between_users(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token_a, user_a = await _register(app_client, "iso-a")
    token_b, _ = await _register(app_client, "iso-b")

    save_r = await app_client.post(
        "/api/job-descriptions",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "title": "Private",
            "company": "Secret",
            "text": "Confidential job description text long enough for validation in this test case.",
            "source": "extension",
        },
    )
    jd_id = save_r.json()["jd_id"]

    session = await create_session()
    session.user_id = user_a
    session.phase3_output = TailoredResumeOutput(
        contact={"name": "Owner", "email": "owner@example.com"},
        summary="Private tailored resume.",
    )
    await update_session(session)

    row = (
        await db_session.execute(select(JobDescription).where(JobDescription.id == uuid.UUID(jd_id)))
    ).scalar_one()
    row.session_id = session.session_id
    await db_session.commit()

    forbidden = await app_client.get(
        f"/api/job-descriptions/{jd_id}/autofill-payload",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert forbidden.status_code == 404


@pytest.mark.asyncio
async def test_autofill_payload_unknown_jd_returns_404(app_client: AsyncClient) -> None:
    token, _ = await _register(app_client, "404")
    missing_id = str(uuid.uuid4())
    r = await app_client.get(
        f"/api/job-descriptions/{missing_id}/autofill-payload",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_job_description_by_id(app_client: AsyncClient) -> None:
    token, _ = await _register(app_client, "get-jd")

    save_r = await app_client.post(
        "/api/job-descriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "url": "https://boards.greenhouse.io/acme/jobs/789",
            "title": "Backend Engineer",
            "company": "Acme",
            "text": "Build APIs with FastAPI and PostgreSQL for our platform engineering team.",
            "source": "extension",
        },
    )
    assert save_r.status_code == 200
    jd_id = save_r.json()["jd_id"]

    get_r = await app_client.get(
        f"/api/job-descriptions/{jd_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_r.status_code == 200, get_r.text
    body = get_r.json()
    assert body["id"] == jd_id
    assert body["title"] == "Backend Engineer"
    assert body["company"] == "Acme"
