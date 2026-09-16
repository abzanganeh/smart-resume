"""JD edits must reset phase status so analysis cannot appear complete with stale output."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.session import PhaseStatus
from app.services.session_store import get_session, update_session

pytestmark = pytest.mark.integration


async def test_changing_jd_resets_phase_status(app_client: AsyncClient) -> None:
    created = await app_client.post("/api/sessions")
    session_id = created.json()["session_id"]

    session = await get_session(session_id)
    assert session is not None
    session.phase1_status = PhaseStatus.done
    session.phase1_output = None
    await update_session(session)

    first = await app_client.post(
        f"/api/sessions/{session_id}/jd",
        json={"jd_text": "Senior Python engineer with FastAPI experience."},
    )
    assert first.status_code == 200

    second = await app_client.post(
        f"/api/sessions/{session_id}/jd",
        json={"jd_text": "Staff Rust engineer building distributed systems."},
    )
    assert second.status_code == 200
    assert second.json()["jd_changed"] is True

    stored = await get_session(session_id)
    assert stored is not None
    assert stored.phase1_status == PhaseStatus.pending
    assert stored.phase2_status == PhaseStatus.pending
    assert stored.phase1_output is None

    check = await app_client.get(f"/api/sessions/{session_id}")
    assert check.json()["phase1_complete"] is False
