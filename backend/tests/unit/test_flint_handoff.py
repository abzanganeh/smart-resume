"""Unit tests for Flint handoff token minting (Strategy B Phase 1.1)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.company_profile import CompanyIntelOutput
from app.models.rewrite import TailoredResumeOutput
from app.models.session import Session
from app.services import flint_handoff
from app.services.session_store import reset_redis_keys_for_tests, update_session
from tests.unit.flint_fixtures import session_with_outputs

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
async def _clean_handoff_store() -> None:
    await reset_redis_keys_for_tests()


@pytest.mark.asyncio
async def test_create_handoff_token_mints_uuid() -> None:
    session = session_with_outputs()
    await update_session(session)

    token, expires_in = await flint_handoff.create_handoff_token(session)
    assert expires_in == 600
    assert len(token) == 36


@pytest.mark.asyncio
async def test_company_intel_survives_redis_round_trip() -> None:
    session = session_with_outputs()
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
    session = session_with_outputs()
    session.phase3_output = None
    with pytest.raises(HTTPException) as exc:
        flint_handoff.build_handoff_payload(session)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_handoff_requires_jd() -> None:
    session = session_with_outputs()
    session.jd_raw = ""
    with pytest.raises(HTTPException) as exc:
        flint_handoff.build_handoff_payload(session)
    assert exc.value.status_code == 422


def test_handoff_uses_account_email_in_resume_summary() -> None:
    session = session_with_outputs()
    session.phase3_output = TailoredResumeOutput(
        contact={"name": "Alireza", "email": "alireza.zanganeh@gmail.com"},
        summary="Engineer",
    )
    payload = flint_handoff.build_handoff_payload(
        session,
        account_email="alireza@zanganehai.com",
    )
    assert "alireza@zanganehai.com" in payload["resume_summary"]
    assert "alireza.zanganeh@gmail.com" not in payload["resume_summary"]


def test_handoff_includes_company_intel_when_present() -> None:
    session = session_with_outputs()
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
    session = session_with_outputs()
    session.company_intel = None
    payload = flint_handoff.build_handoff_payload(session)
    assert "company_intel" not in payload


def test_handoff_omits_company_intel_when_empty() -> None:
    session = session_with_outputs()
    session.company_intel = CompanyIntelOutput(company_name="Acme Corp")
    payload = flint_handoff.build_handoff_payload(session)
    assert "company_intel" not in payload


@pytest.mark.asyncio
async def test_create_handoff_fetches_company_intel_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    session = session_with_outputs()
    session.jd_raw = FISHER_JD
    await update_session(session)

    async def _fake_ensure(target: Session) -> None:
        target.company_intel = CompanyIntelOutput(
            company_name="Fisher Investments",
            mission="Bettering the investment universe",
            values=["Learning", "Collaboration"],
            culture_notes="Inclusive, in-office culture with Great Place to Work emphasis",
        )

    monkeypatch.setattr(flint_handoff, "ensure_session_company_intel", _fake_ensure)

    token, _ = await flint_handoff.create_handoff_token(session)
    payload = await flint_handoff.redeem_handoff_token(token, client_ip="127.0.0.1")

    assert "company_intel" in payload
    assert payload["company_intel"]["mission"] == "Bettering the investment universe"


FISHER_JD = """Senior AI Developer
Fisher Investments
Camas, Washington
Join Fisher Investments to build enterprise AI solutions.
"""


@pytest.mark.asyncio
async def test_assert_session_owned_rejects_wrong_user() -> None:
    session = session_with_outputs(user_id="owner-a")
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
