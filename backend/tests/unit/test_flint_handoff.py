"""Unit tests for Flint handoff token minting (Strategy B Phase 1.1)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.company_profile import CompanyIntelOutput
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
