"""Cover letter generation, export, and quota enforcement."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditOutput, KeywordCoverage
from app.models.cover_letter import CoverLetterOutput
from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput
from app.models.session import PhaseStatus
from app.services.billing.credits import consume_credit
from app.models.billing import CreditKind
from app.services.session_store import create_session, update_session
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration

SAMPLE_COVER_LETTER = CoverLetterOutput(
    body_markdown=(
        "Dear Hiring Manager,\n\n"
        "I am excited to apply for the Backend Engineer role. "
        "At Acme I built Python APIs serving millions of requests.\n\n"
        "Thank you for your consideration.\n\nJane Doe"
    ),
    body_plain=(
        "Dear Hiring Manager,\n\n"
        "I am excited to apply for the Backend Engineer role. "
        "At Acme I built Python APIs serving millions of requests.\n\n"
        "Thank you for your consideration.\n\nJane Doe"
    ),
    word_count=32,
    tone="balanced",
    keywords_used=["Python", "Backend Engineer"],
)


def _sample_tailored() -> TailoredResumeOutput:
    return TailoredResumeOutput(
        summary="Backend engineer with Python experience.",
        skills=["Python", "FastAPI"],
        experience=[
            TailoredExperienceEntry(
                title="Engineer",
                company="Acme",
                dates="2020–2024",
                bullets=["Built Python APIs"],
            )
        ],
    )


async def _register(client: AsyncClient) -> str:
    payload = {**REGISTER_PAYLOAD, "email": f"cover-{uuid.uuid4().hex[:8]}@example.com"}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


async def _seed_session_with_resume() -> str:
    session = await create_session()
    session.phase3_output = _sample_tailored()
    session.phase3_status = PhaseStatus.done
    session.phase2_output = AuditOutput(
        keyword_coverage=KeywordCoverage(),
        overall_score=70,
        summary="Audit ok",
    )
    session.phase2_status = PhaseStatus.done
    session.jd_raw = "Backend Engineer with Python and FastAPI."
    await update_session(session)
    return session.session_id


async def _parse_sse_events(raw: str) -> list[dict]:
    events: list[dict] = []
    for block in raw.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


async def test_generate_cover_letter_and_export_pdf(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = await _seed_session_with_resume()
    token = await _register(app_client)

    async def fake_run(session, llm, event_queue, *, tone="balanced", custom_hook=None):
        await event_queue.put({"event": "progress", "message": "Drafting…"})
        return SAMPLE_COVER_LETTER

    monkeypatch.setattr("app.agent.cover_letter.run", fake_run)

    res = await app_client.post(
        f"/api/sessions/{session_id}/cover-letter",
        json={"tone": "balanced"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    events = await _parse_sse_events(res.text)
    assert any(e.get("event") == "done" for e in events)

    export_res = await app_client.get(
        f"/api/sessions/{session_id}/cover-letter/export?format=pdf"
    )
    assert export_res.status_code == 200, export_res.text
    assert export_res.headers["content-type"] == "application/pdf"
    assert len(export_res.content) > 100


async def test_free_user_zero_credits_returns_402(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = await _seed_session_with_resume()

    email = f"nocredits-{uuid.uuid4().hex[:8]}@example.com"
    payload = {**REGISTER_PAYLOAD, "email": email}
    reg = await app_client.post("/api/auth/register", json=payload)
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]

    user = await db_session.get(User, uuid.UUID(user_id))
    assert user is not None
    balance = 6
    while balance > 0:
        await consume_credit(
            db_session,
            user_id=user.id,
            credit_kind=CreditKind.free,
            reason="resume_build",
        )
        balance -= 1
    await db_session.commit()

    async def fake_run(session, llm, event_queue, *, tone="balanced", custom_hook=None):
        return SAMPLE_COVER_LETTER

    monkeypatch.setattr("app.agent.cover_letter.run", fake_run)

    res = await app_client.post(
        f"/api/sessions/{session_id}/cover-letter",
        json={"tone": "formal"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 402, res.text
    body = res.json()
    assert body["detail"]["code"] == "insufficient_credits"


async def test_cover_letter_requires_tailored_resume(app_client: AsyncClient) -> None:
    session = await create_session()
    token = await _register(app_client)

    res = await app_client.post(
        f"/api/sessions/{session.session_id}/cover-letter",
        json={"tone": "warm"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "resume_required"
