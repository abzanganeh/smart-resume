"""Scoped Phase 3 regeneration — merge behavior and stale markers."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from app.agent.phase3_rewrite import _merge_scoped_output, run
from app.models.audit import AuditOutput, KeywordCoverage
from app.models.keywords import KeywordExtractionOutput
from app.models.rewrite import TailoredExperienceEntry, TailoredResumeOutput
from app.models.session import PhaseRunScope, PhaseStatus, Session
from app.services.session_store import create_session, get_session, update_session

pytestmark = pytest.mark.integration


def _sample_tailored() -> TailoredResumeOutput:
    return TailoredResumeOutput(
        summary="Original summary with Python and FastAPI keywords.",
        skills=["Python", "SQL"],
        experience=[
            TailoredExperienceEntry(
                title="Engineer",
                company="Acme",
                dates="2020–2024",
                bullets=["Built APIs", "Led team"],
            ),
            TailoredExperienceEntry(
                title="Intern",
                company="Beta",
                dates="2019",
                bullets=["Wrote tests"],
            ),
        ],
    )


async def test_merge_scoped_experience_section_preserves_other_sections() -> None:
    existing = _sample_tailored()
    partial = TailoredResumeOutput(
        experience=[
            TailoredExperienceEntry(
                title="Engineer",
                company="Acme",
                dates="2020–2024",
                bullets=["Rewrote APIs with FastAPI", "Scaled platform"],
            )
        ]
    )
    scope = PhaseRunScope(section="experience", company="Acme")

    merged = _merge_scoped_output(existing, partial, scope)

    assert merged.summary == existing.summary
    assert merged.skills == existing.skills
    assert len(merged.experience) == 2
    assert merged.experience[0].company == "Acme"
    assert merged.experience[0].bullets[0].startswith("Rewrote")
    assert merged.experience[1].company == "Beta"


async def test_merge_scoped_bullet_updates_single_bullet() -> None:
    existing = _sample_tailored()
    partial = TailoredResumeOutput(
        experience=[
            TailoredExperienceEntry(
                company="Acme",
                bullets=["New bullet one"],
            )
        ]
    )
    scope = PhaseRunScope(section="experience", company="Acme", bullet_index=0)

    merged = _merge_scoped_output(existing, partial, scope)

    assert merged.experience[0].bullets[0] == "New bullet one"
    assert merged.experience[0].bullets[1] == "Led team"
    assert merged.summary == existing.summary


@pytest.mark.asyncio
async def test_scoped_run_preserves_unscoped_sections(monkeypatch) -> None:
    """Integration: scoped regen merges LLM partial output without wiping other sections."""
    session = await create_session()
    session.phase1_output = KeywordExtractionOutput()
    session.phase2_output = AuditOutput(
        keyword_coverage=KeywordCoverage(present=["Python"]),
        overall_score=70,
        summary="Audit ok",
    )
    session.phase3_output = _sample_tailored()
    session.phase1_status = PhaseStatus.done
    session.phase2_status = PhaseStatus.done
    session.phase3_status = PhaseStatus.done
    await update_session(session)

    partial = TailoredResumeOutput(
        summary="Should be ignored for company-scoped regen",
        experience=[
            TailoredExperienceEntry(
                title="Engineer",
                company="Acme",
                dates="2020–2024",
                bullets=["Scoped rewrite bullet", "Led team"],
            )
        ],
    )

    async def fake_complete(*args, **kwargs):
        return partial

    monkeypatch.setattr("app.agent.phase3_rewrite.complete_structured", fake_complete)

    class FakeLLM:
        provider_name = "test"
        model_name = "test-model"

    queue: asyncio.Queue = asyncio.Queue()
    scope = PhaseRunScope(section="experience", company="Acme")
    refreshed = await get_session(session.session_id)
    assert refreshed is not None

    output = await run(refreshed, FakeLLM(), queue, scope=scope)

    assert output.summary == _sample_tailored().summary
    assert output.skills == _sample_tailored().skills
    assert output.experience[0].bullets[0] == "Scoped rewrite bullet"
    assert output.experience[1].company == "Beta"


@pytest.mark.asyncio
async def test_patch_audit_marks_downstream_stale(app_client) -> None:
    session = await create_session()
    session.phase2_output = AuditOutput(
        keyword_coverage=KeywordCoverage(),
        overall_score=55,
        summary="Before edit",
    )
    session.phase2_status = PhaseStatus.done
    await update_session(session)

    res = await app_client.patch(
        f"/api/sessions/{session.session_id}/audit",
        json={"summary": "After manual edit"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["stale"]["3"] is not None
    assert body["stale"]["4"] is not None

    check = await app_client.get(f"/api/sessions/{session.session_id}")
    assert check.json()["stale"]["3"] is not None


@pytest.mark.asyncio
async def test_subscriber_scoped_regen_does_not_increment_resumes_used(
    db_session, monkeypatch
) -> None:
    from app.models.billing import (
        Subscription,
        SubscriptionBillingCycle,
        SubscriptionPlan,
        SubscriptionStatus,
    )
    from app.models.user import AuthProvider, User, UserTier
    from app.services.billing.quota import check_quota_for_section_regen

    user = User(
        id=uuid.uuid4(),
        email="sub@example.com",
        display_name="sub",
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.pro,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db_session.add(user)
    now = datetime.now(timezone.utc)
    sub = Subscription(
        id=uuid.uuid4(),
        user_id=user.id,
        plan=SubscriptionPlan.monthly,
        billing_cycle=SubscriptionBillingCycle.recurring,
        status=SubscriptionStatus.active,
        period_start=now,
        period_end=now.replace(year=now.year + 1),
        cancel_at_period_end=False,
        stripe_customer_id="cus",
        stripe_subscription_id="sub",
        stripe_price_id="price",
        resumes_used=5,
    )
    db_session.add(sub)
    await db_session.commit()

    decision = await check_quota_for_section_regen(
        db_session, user=user, session_id="sess-1"
    )
    await db_session.refresh(sub)

    assert decision.charged_to == "subscription_section_regen"
    assert sub.resumes_used == 5
