"""Regression: signup credits are visible but unspendable until email verification."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration

LONG_RESUME = (
    "Jane Doe — Senior Backend Engineer with eight years of experience building "
    "Python FastAPI services at Acme Corp serving millions of requests daily. "
    "Designed PostgreSQL schemas, Redis caching layers, and CI/CD pipelines. "
    "Led on-call rotation and mentored junior engineers across two product teams."
)


@pytest.mark.asyncio
async def test_unverified_user_sees_locked_credits_on_me(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "locked-credits@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    body = reg.json()["user"]
    assert body["credit_balance"] == 3
    assert body["spendable_credit_balance"] == 0
    assert body["credits_locked_until_verification"] is True
    assert body["email_verified_at"] is None


@pytest.mark.asyncio
async def test_verifying_email_unlocks_spendable_credits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "unlock-credits@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    token = reg.json()["access_token"]

    user = (
        await db_session.execute(select(User).where(User.email == payload["email"]))
    ).scalar_one()
    from datetime import datetime, timezone

    user.email_verified_at = datetime.now(timezone.utc)
    await db_session.commit()

    me = await app_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["credit_balance"] == 3
    assert body["spendable_credit_balance"] == 3
    assert body["credits_locked_until_verification"] is False


@pytest.mark.asyncio
async def test_unverified_user_cannot_deduct_flint_credits(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "no-spend@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    token = reg.json()["access_token"]

    resp = await app_client.post(
        "/api/credits/deduct",
        json={
            "action": "digest_extraction",
            "product": "career_flint",
            "session_id": "test-session",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "credits_locked_until_verification"


@pytest.mark.asyncio
async def test_locked_fields_present_on_subscription_and_dashboard(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "fields@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    sub = await app_client.get("/api/subscriptions/current", headers=headers)
    assert sub.status_code == 200, sub.text
    sub_body = sub.json()
    assert sub_body["credit_balance"] == 3
    assert sub_body["spendable_credit_balance"] == 0
    assert sub_body["credits_locked_until_verification"] is True

    dash = await app_client.get("/api/dashboard/summary", headers=headers)
    assert dash.status_code == 200, dash.text
    dash_body = dash.json()
    assert dash_body["credit_balance"] == 3
    assert dash_body["spendable_credit_balance"] == 0
    assert dash_body["credits_locked_until_verification"] is True


@pytest.mark.asyncio
async def test_unverified_user_cannot_upload_master_resume_with_llm(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "no-llm-unverified@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]

    resp = await app_client.post(
        "/api/profile/resume",
        data={"text": "Jane Doe\nSoftware Engineer\nBuilt APIs in Python."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "email_verification_required"


@pytest.mark.asyncio
async def test_verify_token_endpoint_marks_user_verified(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "verify-link@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    assert reg.status_code == 201, reg.text

    user = (
        await db_session.execute(select(User).where(User.email == payload["email"]))
    ).scalar_one()
    assert user.email_verified_at is None

    from app.services.auth.email import make_email_verification_token

    verify_token = make_email_verification_token(user.id)
    resp = await app_client.get(f"/api/auth/verify/{verify_token}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == payload["email"]

    await db_session.refresh(user)
    assert user.email_verified_at is not None


@pytest.mark.asyncio
async def test_unverified_user_cannot_structure_session_resume_with_bearer(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "no-session-llm@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]

    created = await app_client.post(
        "/api/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]

    resp = await app_client.post(
        f"/api/sessions/{session_id}/resume/text",
        json={"text": LONG_RESUME},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "email_verification_required"


@pytest.mark.asyncio
async def test_claimed_session_resume_without_bearer_blocks_unverified(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "no-resume-no-bearer@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    token = reg.json()["access_token"]

    created = await app_client.post(
        "/api/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = created.json()["session_id"]

    resp = await app_client.post(
        f"/api/sessions/{session_id}/resume/text",
        json={"text": LONG_RESUME},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "email_verification_required"


@pytest.mark.asyncio
async def test_anonymous_session_resume_without_bearer_is_not_verify_gated(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guest tailoring still works without login; gate is not email_verification."""
    created = await app_client.post("/api/sessions")
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]

    async def fake_structure(raw_text: str, llm) -> object:
        from app.models.resume import ParsedResume

        return ParsedResume()

    monkeypatch.setattr(
        "app.routers.resume._structure_resume",
        fake_structure,
    )

    resp = await app_client.post(
        f"/api/sessions/{session_id}/resume/text",
        json={"text": LONG_RESUME},
    )
    assert resp.status_code != 403 or resp.json().get("detail", {}).get("code") != (
        "email_verification_required"
    )


@pytest.mark.asyncio
async def test_unverified_user_cannot_chat_claimed_session(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "no-chat@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    token = reg.json()["access_token"]

    created = await app_client.post(
        "/api/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = created.json()["session_id"]

    for headers in (
        {"Authorization": f"Bearer {token}"},
        {},
    ):
        resp = await app_client.post(
            f"/api/sessions/{session_id}/chat",
            json={"message": "Add a bullet about Kubernetes"},
            headers=headers,
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "email_verification_required"


@pytest.mark.asyncio
async def test_unverified_user_cannot_get_title_suggestions(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "no-titles@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    token = reg.json()["access_token"]

    resp = await app_client.get(
        "/api/jobs/title-suggestions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "email_verification_required"


@pytest.mark.asyncio
async def test_verify_invalid_token_returns_code(app_client: AsyncClient) -> None:
    resp = await app_client.get("/api/auth/verify/not-a-valid-jwt")
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["code"] == "verify_token_invalid"


@pytest.mark.asyncio
async def test_verify_token_unlocks_spendable_credits_via_me(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "verify-me-credits@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    token = reg.json()["access_token"]

    from app.services.auth.email import make_email_verification_token

    user = (
        await db_session.execute(select(User).where(User.email == payload["email"]))
    ).scalar_one()
    verify_token = make_email_verification_token(user.id)
    verified = await app_client.get(f"/api/auth/verify/{verify_token}")
    assert verified.status_code == 200, verified.text

    me = await app_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["spendable_credit_balance"] == 3
    assert body["credits_locked_until_verification"] is False


@pytest.mark.asyncio
async def test_unverified_user_cannot_run_fit_analyze(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "no-fit-analyze@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]

    resp = await app_client.post(
        "/api/fit/analyze",
        data={"jd_text": "Backend engineer — Python, FastAPI."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "email_verification_required"


@pytest.mark.asyncio
async def test_unverified_user_cannot_verify_llm_key(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "no-llm-verify@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]

    resp = await app_client.post(
        "/api/llm/verify",
        json={"provider": "groq", "model": "llama-3.3-70b-versatile"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "email_verification_required"


@pytest.mark.asyncio
async def test_assert_user_email_verified_fails_closed_on_bad_input(
    db_session: AsyncSession,
) -> None:
    """F2 regression: malformed/absent principals must deny, never allow, LLM spend."""
    from fastapi import HTTPException

    from app.services.auth.dependencies import assert_user_email_verified

    with pytest.raises(HTTPException) as bad_uuid_exc:
        await assert_user_email_verified(db_session, "not-a-uuid")
    assert bad_uuid_exc.value.status_code == 403

    with pytest.raises(HTTPException) as missing_user_exc:
        await assert_user_email_verified(db_session, uuid.uuid4())
    assert missing_user_exc.value.status_code == 401


@pytest.mark.asyncio
async def test_unverified_user_cannot_fit_saved_job(
    app_client: AsyncClient,
) -> None:
    payload = {**REGISTER_PAYLOAD, "email": "no-job-fit@example.com"}
    reg = await app_client.post("/api/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]

    resp = await app_client.post(
        f"/api/jobs/{uuid.uuid4()}/fit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "email_verification_required"
