"""Unit tests for Flint handoff token service (in-memory Redis fallback)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.models.company_profile import CompanyIntelOutput
from app.models.keywords import KeywordExtractionOutput, RoleContext
from app.models.rewrite import TailoredResumeOutput
from app.models.session import Session
from app.services import flint_handoff
from app.services.session_store import reset_redis_keys_for_tests, update_session


@pytest.fixture(autouse=True)
async def _clean_handoff_store() -> None:
    await reset_redis_keys_for_tests()


def _session_with_outputs(*, user_id: str | None = "user-1") -> Session:
    return Session(
        session_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
        user_id=user_id,
        jd_raw="Senior Engineer at Acme Corp\nBuild distributed systems.",
        phase1_output=KeywordExtractionOutput(
            role_context=RoleContext(
                career_level="senior",
                primary_domain="platform engineering",
            ),
        ),
        phase3_output=TailoredResumeOutput(
            contact={"name": "Alex", "title": "Senior Engineer"},
            summary="Experienced backend engineer.",
            skills=["Rust", "Python"],
        ),
    )


@pytest.mark.asyncio
async def test_create_and_redeem_handoff_token() -> None:
    session = _session_with_outputs()
    await update_session(session)

    token, expires_in = await flint_handoff.create_handoff_token(session)
    assert expires_in == 600
    assert len(token) == 36

    payload = await flint_handoff.redeem_handoff_token(token, client_ip="127.0.0.1")
    assert payload["jd_text"].startswith("Senior Engineer")
    assert payload["session_type"] == "interview"
    assert payload["domain"] == "platform engineering"
    assert len(payload["resume_summary"]) <= 2000

    with pytest.raises(HTTPException) as exc:
        await flint_handoff.redeem_handoff_token(token, client_ip="127.0.0.1")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_company_intel_survives_redis_round_trip() -> None:
    session = _session_with_outputs()
    session.company_intel = CompanyIntelOutput(
        company_name="Acme Corp",
        mission="Build software that matters",
        values=["Bias for Action", "Customer Obsession"],
        culture_notes="Fast-paced, high-ownership",
    )
    await update_session(session)

    token, _ = await flint_handoff.create_handoff_token(session)
    payload = await flint_handoff.redeem_handoff_token(token, client_ip="127.0.0.1")

    assert "company_intel" in payload
    ci = payload["company_intel"]
    assert ci["mission"] == "Build software that matters"
    assert ci["values"] == ["Bias for Action", "Customer Obsession"]
    assert ci["culture_notes"] == "Fast-paced, high-ownership"


@pytest.mark.asyncio
async def test_handoff_requires_phase3() -> None:
    session = _session_with_outputs()
    session.phase3_output = None
    with pytest.raises(HTTPException) as exc:
        flint_handoff.build_handoff_payload(session)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_ten_requests() -> None:
    for _ in range(10):
        with pytest.raises(HTTPException):
            await flint_handoff.redeem_handoff_token("missing-token", client_ip="10.0.0.9")

    with pytest.raises(HTTPException) as exc:
        await flint_handoff.redeem_handoff_token("missing-token", client_ip="10.0.0.9")
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_handoff_requires_jd() -> None:
    session = _session_with_outputs()
    session.jd_raw = ""
    with pytest.raises(HTTPException) as exc:
        flint_handoff.build_handoff_payload(session)
    assert exc.value.status_code == 422


def test_handoff_includes_company_intel_when_present() -> None:
    session = _session_with_outputs()
    session.company_intel = CompanyIntelOutput(
        company_name="Acme Corp",
        mission="Build software that matters",
        values=["Bias for Action", "Customer Obsession"],
        culture_notes="Fast-paced, high-ownership",
    )
    payload = flint_handoff.build_handoff_payload(session)
    assert "company_intel" in payload
    ci = payload["company_intel"]
    assert ci["mission"] == "Build software that matters"
    assert ci["values"] == ["Bias for Action", "Customer Obsession"]
    assert ci["culture_notes"] == "Fast-paced, high-ownership"


def test_handoff_omits_company_intel_when_absent() -> None:
    session = _session_with_outputs()
    session.company_intel = None
    payload = flint_handoff.build_handoff_payload(session)
    assert "company_intel" not in payload


def test_handoff_omits_company_intel_when_empty() -> None:
    session = _session_with_outputs()
    session.company_intel = CompanyIntelOutput(company_name="Acme Corp")  # mission/values/culture all empty
    payload = flint_handoff.build_handoff_payload(session)
    assert "company_intel" not in payload


@pytest.mark.asyncio
async def test_assert_session_owned_rejects_wrong_user() -> None:
    session = _session_with_outputs(user_id="owner-a")
    await update_session(session)

    with pytest.raises(HTTPException) as exc:
        await flint_handoff.assert_session_owned(session.session_id, "owner-b")
    assert exc.value.status_code == 403
