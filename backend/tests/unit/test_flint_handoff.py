"""Unit tests for Flint handoff token service (in-memory Redis fallback)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

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


@pytest.mark.asyncio
async def test_assert_session_owned_rejects_wrong_user() -> None:
    session = _session_with_outputs(user_id="owner-a")
    await update_session(session)

    with pytest.raises(HTTPException) as exc:
        await flint_handoff.assert_session_owned(session.session_id, "owner-b")
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "company,title,expected",
    [
        ("", "", "New Interview"),
        ("Acme", "", "Acme"),
        ("", "Senior Engineer", "Senior Engineer"),
        ("Acme", "Senior Engineer", "Acme — Senior Engineer"),
        ("   ", "Engineer", "Engineer"),
    ],
)
def test_jd_handoff_session_name(company: str, title: str, expected: str) -> None:
    """Session name derivation handles every empty/non-empty company/title combo."""
    assert flint_handoff._derive_jd_session_name(company.strip(), title.strip()) == expected


@pytest.mark.asyncio
async def test_create_jd_handoff_token_round_trip() -> None:
    """JD-only handoff payload is well-formed and round-trips through Redis."""
    token, expires_in = await flint_handoff.create_jd_handoff_token(
        jd_id="00000000-0000-0000-0000-000000000001",
        jd_text="  Build distributed systems at Acme Corp.  ",
        title="Senior Engineer",
        company="Acme Corp",
        user_id="user-1",
    )
    assert expires_in == 600
    assert len(token) == 36

    payload = await flint_handoff.redeem_handoff_token(token, client_ip="127.0.0.1")
    assert payload["session_name"] == "Acme Corp — Senior Engineer"
    assert payload["jd_text"].startswith("Build distributed systems")
    assert payload["resume_summary"] == ""
    assert payload["smart_resume_session_id"] == ""
    assert payload["jd_id"] == "00000000-0000-0000-0000-000000000001"
    assert payload["export_version"] == flint_handoff._EXPORT_VERSION
