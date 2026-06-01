"""Integration tests for ResumeRecord creation on Phase 4 completion."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditOutput, KeywordCoverage
from app.models.dashboard import AtsScoreHistory, ResumeRecord, ResumeRecordStatus
from app.models.qa import QAOutput
from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput
from app.models.session import PhaseStatus
from app.models.userinfo import UserInfo
from app.services.dashboard.resume_record import compute_jd_text_hash
from app.services.session_store import create_session, update_session
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


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


async def _register(client: AsyncClient) -> tuple[str, uuid.UUID]:
    payload = {**REGISTER_PAYLOAD, "email": f"dash-{uuid.uuid4().hex[:8]}@example.com"}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    return body["access_token"], uuid.UUID(body["user"]["id"])


async def test_phase4_completion_creates_resume_record(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, user_id = await _register(app_client)

    session = await create_session()
    session.user_id = str(user_id)
    session.jd_raw = "Backend Engineer at Acme Corp\nPython, FastAPI required."
    session.user_info = UserInfo(
        name="Jane",
        email="jane@example.com",
        career_stage="mid",
        target_role="Backend Engineer",
    )
    session.phase1_status = PhaseStatus.done
    session.phase2_status = PhaseStatus.done
    session.phase3_status = PhaseStatus.done
    session.phase3_output = _sample_tailored()
    session.phase2_output = AuditOutput(
        keyword_coverage=KeywordCoverage(),
        overall_score=70,
        summary="Audit ok",
    )
    await update_session(session)

    qa_output = QAOutput(
        checklist=[],
        overall_status="pass",
        ats_score=82,
        score_ceiling=90,
    )

    async def fake_phase4(session_obj, llm, event_queue):
        return qa_output

    monkeypatch.setattr("app.agent.phase4_qa.run", fake_phase4)

    from app.llm.base import LLMClient, LLMMessage, LLMResponse

    class _FakeLLM(LLMClient):
        @property
        def provider_name(self) -> str:
            return "openai"

        @property
        def model_name(self) -> str:
            return "gpt-test"

        @property
        def context_window(self) -> int:
            return 8192

        @property
        def supports_structured_output(self) -> bool:
            return True

        async def complete(
            self,
            messages: list[LLMMessage],
            *,
            response_schema: dict | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.2,
        ) -> LLMResponse:
            return LLMResponse(
                content="",
                input_tokens=0,
                output_tokens=0,
                model=self.model_name,
                provider=self.provider_name,
            )

        async def stream(self, messages, *, max_tokens=4096, temperature=0.2):
            if False:
                yield ""

    from app.agent import orchestrator

    queue: asyncio.Queue = asyncio.Queue()
    await orchestrator.run_phase(session.session_id, 4, _FakeLLM(), queue)

    jd_hash = compute_jd_text_hash(session.jd_raw)
    record = (
        await db_session.execute(
            select(ResumeRecord).where(
                ResumeRecord.user_id == user_id,
                ResumeRecord.jd_text_hash == jd_hash,
            )
        )
    ).scalar_one_or_none()

    assert record is not None
    assert record.current_ats_score == 82
    assert record.starting_ats_score == 82
    assert record.session_id == session.session_id
    assert record.jd_title == "Backend Engineer"

    history = (
        await db_session.execute(
            select(AtsScoreHistory).where(
                AtsScoreHistory.resume_record_id == record.id
            )
        )
    ).scalars().all()
    assert len(history) == 1
    assert history[0].score == 82
    assert history[0].recalc_type.value == "initial"

    list_res = await app_client.get(
        "/api/resumes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_res.status_code == 200, list_res.text
    body = list_res.json()
    assert body["total"] == 1
    assert body["items"][0]["current_ats_score"] == 82


async def test_resume_list_status_filter(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client)
    now = datetime.now(timezone.utc)

    draft = ResumeRecord(
        user_id=user_id,
        session_id="sess-draft",
        jd_title="Draft Role",
        jd_company="Alpha",
        jd_text_hash="hash-draft",
        current_ats_score=70,
        starting_ats_score=65,
        status=ResumeRecordStatus.draft,
        created_at=now,
        updated_at=now,
    )
    applied = ResumeRecord(
        user_id=user_id,
        session_id="sess-applied",
        jd_title="Applied Role",
        jd_company="Beta",
        jd_text_hash="hash-applied",
        current_ats_score=80,
        starting_ats_score=75,
        status=ResumeRecordStatus.applied,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([draft, applied])
    await db_session.flush()

    all_res = await app_client.get(
        "/api/resumes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert all_res.json()["total"] == 2

    filtered = await app_client.get(
        "/api/resumes?status=applied",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert filtered.status_code == 200
    data = filtered.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "applied"
    assert data["items"][0]["jd_title"] == "Applied Role"
