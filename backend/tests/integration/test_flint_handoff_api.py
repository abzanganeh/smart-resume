"""Integration tests for Flint handoff HTTP routes."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.rewrite import TailoredResumeOutput
from app.services.session_store import create_session, update_session
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


async def _register(client: AsyncClient) -> tuple[str, str]:
    payload = {**REGISTER_PAYLOAD, "email": f"flint-{uuid.uuid4().hex[:8]}@example.com"}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    return body["access_token"], body["user"]["id"]


@pytest.mark.asyncio
async def test_flint_handoff_create_and_redeem(app_client: AsyncClient) -> None:
    token, user_id = await _register(app_client)

    session = await create_session()
    session.user_id = user_id
    session.jd_raw = "Staff Engineer — Platform team\nKubernetes, Rust, distributed systems."
    session.phase3_output = TailoredResumeOutput(
        contact={"name": "Sam", "title": "Staff Engineer"},
        summary="Platform engineer with 8 years experience.",
        skills=["Rust", "Kubernetes"],
    )
    await update_session(session)

    create_r = await app_client.post(
        f"/api/sessions/{session.session_id}/flint-handoff",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_r.status_code == 200, create_r.text
    handoff = create_r.json()
    assert "token" in handoff
    assert handoff["expires_in"] == 600

    redeem_r = await app_client.post(
        "/api/flint/context",
        json={"token": handoff["token"]},
    )
    assert redeem_r.status_code == 200, redeem_r.text
    ctx = redeem_r.json()
    assert ctx["jd_text"].startswith("Staff Engineer")
    assert ctx["smart_resume_session_id"] == session.session_id
    assert ctx["session_type"] == "interview"

    second = await app_client.post(
        "/api/flint/context",
        json={"token": handoff["token"]},
    )
    assert second.status_code == 404


@pytest.mark.asyncio
async def test_flint_handoff_requires_auth(app_client: AsyncClient) -> None:
    session = await create_session()
    session.jd_raw = "Job description text here for testing minimum content length."
    session.phase3_output = TailoredResumeOutput(summary="Tailored resume.")
    await update_session(session)

    r = await app_client.post(f"/api/sessions/{session.session_id}/flint-handoff")
    assert r.status_code == 401
