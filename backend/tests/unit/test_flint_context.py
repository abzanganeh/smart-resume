"""Unit tests for POST /api/flint/context redeem path (Strategy B Phase 1.2)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services import flint_handoff
from app.services.session_store import reset_redis_keys_for_tests, update_session
from tests.unit.flint_fixtures import session_with_outputs

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
async def _clean_handoff_store() -> None:
    await reset_redis_keys_for_tests()


@pytest.mark.asyncio
async def test_valid_token_returns_payload() -> None:
    session = session_with_outputs()
    await update_session(session)

    token, _ = await flint_handoff.create_handoff_token(session)
    payload = await flint_handoff.redeem_handoff_token(token, client_ip="127.0.0.1")

    assert payload["jd_text"].startswith("Senior Engineer")
    assert payload["session_type"] == "interview"
    assert payload["domain"] == "platform engineering"
    assert len(payload["resume_summary"]) <= 2000


@pytest.mark.asyncio
async def test_second_redeem_returns_404() -> None:
    session = session_with_outputs()
    await update_session(session)

    token, _ = await flint_handoff.create_handoff_token(session)
    await flint_handoff.redeem_handoff_token(token, client_ip="127.0.0.1")

    with pytest.raises(HTTPException) as exc:
        await flint_handoff.redeem_handoff_token(token, client_ip="127.0.0.1")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_missing_token_returns_404() -> None:
    with pytest.raises(HTTPException) as exc:
        await flint_handoff.redeem_handoff_token("missing-token", client_ip="127.0.0.1")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_malformed_token_returns_404() -> None:
    with pytest.raises(HTTPException) as exc:
        await flint_handoff.redeem_handoff_token("", client_ip="127.0.0.1")
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await flint_handoff.redeem_handoff_token("x" * 65, client_ip="127.0.0.1")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_ten_requests() -> None:
    for _ in range(10):
        with pytest.raises(HTTPException):
            await flint_handoff.redeem_handoff_token("missing-token", client_ip="10.0.0.9")

    with pytest.raises(HTTPException) as exc:
        await flint_handoff.redeem_handoff_token("missing-token", client_ip="10.0.0.9")
    assert exc.value.status_code == 429


def test_flint_context_response_preserves_company_intel() -> None:
    """Redeem HTTP model must not strip company_intel from the Redis payload."""
    from app.routers.flint_handoff import FlintContextResponse

    payload = {
        "session_name": "Acme — Senior Engineer",
        "session_type": "interview",
        "domain": "platform engineering",
        "jd_text": "Senior Engineer role",
        "resume_summary": "Experienced engineer.",
        "smart_resume_session_id": "sr-1",
        "export_version": 1,
        "company_intel": {
            "mission": "Build software that matters",
            "values": ["Bias for Action"],
            "culture_notes": "Fast-paced",
        },
    }
    response = FlintContextResponse.model_validate(payload)
    assert response.company_intel is not None
    assert response.company_intel.mission == "Build software that matters"
    assert response.company_intel.values == ["Bias for Action"]
    assert response.company_intel.culture_notes == "Fast-paced"

    serialized = response.model_dump(mode="json")
    assert serialized["company_intel"]["mission"] == "Build software that matters"


def test_flint_context_response_omits_company_intel_when_absent() -> None:
    from app.routers.flint_handoff import FlintContextResponse

    payload = {
        "session_name": "Acme — Senior Engineer",
        "session_type": "interview",
        "domain": "platform engineering",
        "jd_text": "Senior Engineer role",
        "resume_summary": "Experienced engineer.",
        "smart_resume_session_id": "sr-1",
        "export_version": 1,
    }
    response = FlintContextResponse.model_validate(payload)
    assert response.company_intel is None


def test_handoff_paths_do_not_log_session_content() -> None:
    """Phase 1 review gate: redeem must not log JD/resume/token at INFO+."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "app"
    sources = [
        root / "services" / "flint_handoff.py",
        root / "routers" / "flint_handoff.py",
    ]
    for path in sources:
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "log." not in stripped:
                continue
            assert "jd_text" not in stripped, f"jd_text logged in {path.name}: {stripped}"
            assert "resume_summary" not in stripped, (
                f"resume_summary logged in {path.name}: {stripped}"
            )

