"""Fail-open regressions in error paths (OWASP A10, A08) — slice A4.

Threat model
------------

A10 ("mishandling of exceptional conditions") is about what the system
grants when something goes *wrong*. The dangerous pattern is a handler
that treats an error as an implicit success: a webhook that can't verify
a signature but writes the row anyway, a credit check that swallows a
database error and lets the work proceed, a lookup that finds nothing
and falls back to something broader than the caller should see.

Every test below drives a failure and asserts the *absence* of value
transferred — no ledger row, no granted credits, no row mutated, no data
returned. Asserting a status code alone is not enough: a handler can
return 400 or 500 after it has already granted something.

Scope
-----

``webhook_handler.py`` and ``billing/subscription.py`` belong to M21,
and ``llm/`` and ``agent/`` belong to M18, so the fail-open coverage
here stays at the boundary those milestones expose rather than
reimplementing their internals.

CI note
-------

Most tests here need Postgres and are marked ``integration``. The
``backend-security`` job runs a pgvector service and exports
``DATABASE_URL``, so they execute there as well as locally; they skip
only where no database is configured. The configuration tests at the
end need neither and always run.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError

from app.config import settings, should_skip_billing_quota
from app.models.billing import (
    CreditKind,
    PlanConfig,
    PlanConfigInterval,
    StripeWebhookEvent,
    StripeWebhookStatus,
)
from app.models.dashboard import ResumeRecord, ResumeRecordStatus
from app.models.rewrite import TailoredResumeOutput
from app.models.user import AuthProvider, CreditTransaction, User, UserTier
from app.services.billing.credits import consume_credit
from app.services.billing.exceptions import InsufficientCreditsError
from app.services.billing.quota import QuotaAction, check_and_increment_quota
from app.services.session_store import create_session, get_session, update_session

WEBHOOK_SECRET = "whsec_test_exceptional_conditions"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def webhook_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    return WEBHOOK_SECRET


def _sign(secret: str, body: bytes, *, timestamp: datetime | None = None) -> dict[str, str]:
    """Build a genuine ``stripe-signature`` header for ``body``.

    Signing for real (rather than patching ``construct_event``) is the
    point: these tests exercise Stripe's verifier, so a change to the
    header format or the tolerance window shows up here.
    """
    ts = str(int((timestamp or datetime.now(timezone.utc)).timestamp()))
    signature = hmac.new(
        secret.encode(), f"{ts}.{body.decode()}".encode(), hashlib.sha256
    ).hexdigest()
    return {"stripe-signature": f"t={ts},v1={signature}"}


async def _seed_user(db: AsyncSession, *, email: str | None = None) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email or f"cond-{uuid.uuid4().hex[:10]}@example.com",
        display_name="Conditions",
        auth_provider=AuthProvider.email,
        password_hash="x",
        tier=UserTier.free,
        credit_balance=0,
        accepted_tos_version="2026-06",
    )
    db.add(user)
    await db.flush()
    await db.commit()
    return user


async def _seed_better_pack_plan(db: AsyncSession) -> None:
    db.add(
        PlanConfig(
            id=uuid.uuid4(),
            code="better_pack",
            stripe_price_id="price_better_pack_conditions",
            amount_cents=499,
            currency="USD",
            interval=PlanConfigInterval.one_time,
            is_active=True,
        )
    )
    await db.commit()


def _checkout_event(event_id: str, user_id: uuid.UUID) -> dict[str, Any]:
    """A ``checkout.session.completed`` event that would grant 5 credits.

    Shaped like a real Stripe event, including the top-level
    ``"object": "event"`` discriminator, because these tests run the
    SDK's own ``construct_event`` rather than patching it.
    """
    return {
        "id": event_id,
        "object": "event",
        "type": "checkout.session.completed",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "livemode": False,
        "data": {
            "object": {
                "id": f"cs_{uuid.uuid4().hex[:16]}",
                "customer": f"cus_{uuid.uuid4().hex[:12]}",
                "client_reference_id": str(user_id),
                "metadata": {"user_id": str(user_id), "code": "better_pack"},
            }
        },
    }


async def _count_credit_rows(db: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(CreditTransaction)
                .where(CreditTransaction.user_id == user_id)
            )
        ).scalar_one()
    )


async def _count_webhook_rows(db: AsyncSession, event_id: str) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(StripeWebhookEvent)
                .where(StripeWebhookEvent.event_id == event_id)
            )
        ).scalar_one()
    )


# ---------------------------------------------------------------------------
# 1. Stripe webhook — signature verification must precede every write
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    "signature_header,label",
    [
        (None, "no signature header"),
        ("", "empty signature header"),
        ("t=1,v1=deadbeef", "wrong signature"),
        ("garbage", "malformed header"),
        ("v1=deadbeef", "missing timestamp"),
    ],
)
async def test_webhook_with_bad_signature_grants_nothing(
    app_client: AsyncClient,
    db_session: AsyncSession,
    webhook_secret: str,
    signature_header: str | None,
    label: str,
) -> None:
    """An unverifiable webhook must not become a credit grant.

    This is the highest-value fail-open test in the milestone: the
    webhook is the one endpoint where an anonymous caller can hand the
    system a payload that mints paid credits. Rejecting with 4xx is
    necessary but not sufficient — the assertions below check that
    neither the ledger nor the event table was touched, because a
    handler that writes first and verifies second would still return
    400.
    """
    user = await _seed_user(db_session)
    await _seed_better_pack_plan(db_session)
    event = _checkout_event(f"evt_badsig_{uuid.uuid4().hex[:10]}", user.id)
    body = json.dumps(event).encode()

    headers = {} if signature_header is None else {"stripe-signature": signature_header}
    response = await app_client.post(
        "/api/webhooks/stripe", content=body, headers=headers
    )

    assert response.status_code in {400, 401}, (
        f"{label}: expected rejection, got {response.status_code} "
        f"{response.text[:300]}"
    )
    assert await _count_credit_rows(db_session, user.id) == 0, (
        f"{label}: an unverified webhook granted credits"
    )
    assert await _count_webhook_rows(db_session, event["id"]) == 0, (
        f"{label}: an unverified webhook was persisted as a Stripe event"
    )


@pytest.mark.integration
async def test_webhook_replay_outside_tolerance_grants_nothing(
    app_client: AsyncClient,
    db_session: AsyncSession,
    webhook_secret: str,
) -> None:
    """A correctly-signed but stale delivery is still a rejection.

    The signature is valid in isolation — it is the timestamp that is
    old. If the tolerance check were ever dropped, a captured webhook
    body would stay replayable forever, and the idempotency table would
    not help because a fresh ``event_id`` can be signed at will.
    """
    user = await _seed_user(db_session)
    await _seed_better_pack_plan(db_session)
    event = _checkout_event(f"evt_replay_{uuid.uuid4().hex[:10]}", user.id)
    body = json.dumps(event).encode()
    stale = datetime.now(timezone.utc) - timedelta(days=2)

    response = await app_client.post(
        "/api/webhooks/stripe",
        content=body,
        headers=_sign(webhook_secret, body, timestamp=stale),
    )

    assert response.status_code in {400, 401}, response.text
    assert await _count_credit_rows(db_session, user.id) == 0
    assert await _count_webhook_rows(db_session, event["id"]) == 0


@pytest.mark.integration
async def test_webhook_without_configured_secret_grants_nothing(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing configuration must fail closed, not skip verification.

    A misconfigured deployment is the classic fail-open trigger: with no
    secret there is nothing to verify against, and "nothing to verify"
    must mean "reject", never "accept unverified".
    """
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    user = await _seed_user(db_session)
    await _seed_better_pack_plan(db_session)
    event = _checkout_event(f"evt_nosecret_{uuid.uuid4().hex[:10]}", user.id)
    body = json.dumps(event).encode()

    response = await app_client.post(
        "/api/webhooks/stripe",
        content=body,
        headers=_sign(WEBHOOK_SECRET, body),
    )

    assert response.status_code in {400, 401, 500, 503}, response.text
    assert await _count_credit_rows(db_session, user.id) == 0
    assert await _count_webhook_rows(db_session, event["id"]) == 0


@pytest.mark.integration
async def test_webhook_positive_control_grants_credits_when_verified(
    app_client: AsyncClient,
    db_session: AsyncSession,
    webhook_secret: str,
) -> None:
    """Positive control for every rejection test above.

    Without this, the whole group could pass because the fixture never
    could have granted anything — a plan row missing, a user id that
    resolves to nobody, a handler that no longer maps the event type.
    """
    user = await _seed_user(db_session)
    await _seed_better_pack_plan(db_session)
    event = _checkout_event(f"evt_ok_{uuid.uuid4().hex[:10]}", user.id)
    body = json.dumps(event).encode()

    response = await app_client.post(
        "/api/webhooks/stripe",
        content=body,
        headers=_sign(webhook_secret, body),
    )

    assert response.status_code == 200, response.text
    assert await _count_credit_rows(db_session, user.id) == 1, (
        "a verified better_pack checkout should grant credits — if this "
        "fails, the rejection tests above are vacuous"
    )


@pytest.mark.integration
async def test_webhook_handler_failure_grants_nothing_and_records_failure(
    app_client: AsyncClient,
    db_session: AsyncSession,
    webhook_secret: str,
) -> None:
    """A handler that raises must leave no partial grant behind.

    The router deliberately splits the work into two transactions so the
    event row survives a handler crash. That split is what makes a
    partial grant possible: if the handler wrote a ledger row and then
    raised, a rollback that only covered the event row would leave the
    credits in place. Assert both halves — no credits, and the failure
    is recorded so a retry (or an operator) can see it.
    """
    user = await _seed_user(db_session)
    # Bind the id now: the router rolls the session back when the handler
    # raises, which expires every loaded attribute.
    user_id = user.id
    await _seed_better_pack_plan(db_session)
    event = _checkout_event(f"evt_boom_{uuid.uuid4().hex[:10]}", user_id)
    body = json.dumps(event).encode()

    with patch(
        "app.services.billing.webhook_handler.dispatch",
        new=AsyncMock(side_effect=RuntimeError("simulated handler crash")),
    ):
        response = await app_client.post(
            "/api/webhooks/stripe",
            content=body,
            headers=_sign(webhook_secret, body),
        )

    assert response.status_code == 500, response.text
    assert response.json()["detail"] == {"code": "handler_failed"}
    assert await _count_credit_rows(db_session, user_id) == 0

    row = (
        await db_session.execute(
            select(StripeWebhookEvent).where(
                StripeWebhookEvent.event_id == event["id"]
            )
        )
    ).scalar_one()
    assert row.status == StripeWebhookStatus.failed
    assert row.processed_at is None
    assert row.last_error, "the failure reason must be recorded for retry triage"


@pytest.mark.integration
async def test_webhook_database_error_mid_dispatch_grants_nothing(
    app_client: AsyncClient,
    db_session: AsyncSession,
    webhook_secret: str,
) -> None:
    """A database failure during dispatch must not be read as success.

    Distinct from the crash above: an ``OperationalError`` can surface
    from anywhere in the handler's transaction, including after a
    partial write. The contract is the same either way — the caller sees
    a 5xx, the event is not marked processed, and no credits exist.
    """
    user = await _seed_user(db_session)
    user_id = user.id
    await _seed_better_pack_plan(db_session)
    event = _checkout_event(f"evt_dberr_{uuid.uuid4().hex[:10]}", user_id)
    body = json.dumps(event).encode()

    db_error = OperationalError("SELECT 1", {}, Exception("connection reset"))
    with patch(
        "app.services.billing.webhook_handler.dispatch",
        new=AsyncMock(side_effect=db_error),
    ):
        response = await app_client.post(
            "/api/webhooks/stripe",
            content=body,
            headers=_sign(webhook_secret, body),
        )

    assert response.status_code >= 500, response.text
    assert await _count_credit_rows(db_session, user_id) == 0

    row = (
        await db_session.execute(
            select(StripeWebhookEvent).where(
                StripeWebhookEvent.event_id == event["id"]
            )
        )
    ).scalar_one()
    assert row.status != StripeWebhookStatus.processed


# ---------------------------------------------------------------------------
# 2. Credit paths — a failed check must never let the work proceed
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_quota_check_propagates_database_errors(
    db_session: AsyncSession,
) -> None:
    """A database error in the credit debit must not return a decision.

    ``check_and_increment_quota`` returning a ``QuotaDecision`` is the
    caller's signal that the user has been charged and the work may
    proceed. If a transient database error were swallowed and turned
    into a decision, every failure window would become free LLM work
    (A10, and denial-of-wallet under LLM06).
    """
    user = await _seed_user(db_session)
    user_id = user.id
    db_error = OperationalError("SELECT 1", {}, Exception("connection reset"))

    with patch(
        "app.services.billing.quota.consume_credit",
        new=AsyncMock(side_effect=db_error),
    ):
        with pytest.raises(OperationalError):
            await check_and_increment_quota(
                db_session,
                user=user,
                action=QuotaAction.resume_build,
                session_id="sess-db-error",
            )

    await db_session.rollback()
    assert await _count_credit_rows(db_session, user_id) == 0


@pytest.mark.integration
async def test_quota_check_denies_a_suspended_user_before_charging(
    db_session: AsyncSession,
) -> None:
    """Suspension is checked before any ledger write.

    The order matters: a suspended user must be refused, not refused
    *and* charged. A stray debit here would silently drain the balance
    of an account that cannot use it.
    """
    from app.services.billing.exceptions import AccountSuspendedError

    user = await _seed_user(db_session)
    user.suspended_at = datetime.now(timezone.utc)
    user.suspension_reason = "manual_admin_suspend"
    await db_session.flush()

    with pytest.raises(AccountSuspendedError):
        await check_and_increment_quota(
            db_session, user=user, action=QuotaAction.resume_build
        )

    assert await _count_credit_rows(db_session, user.id) == 0


@pytest.mark.integration
async def test_consume_credit_at_zero_balance_writes_no_ledger_row(
    db_session: AsyncSession,
) -> None:
    """Refusal must be total: no debit row, no cached-balance drift.

    ``consume_credit`` inserts the debit *after* the balance check, and
    it also maintains the denormalized ``users.credit_balance`` cache.
    An insufficient-credits path that had already written either one
    would leave the ledger and the cache disagreeing, and the ledger is
    the source of truth for every later read (§7.5).
    """
    user = await _seed_user(db_session)

    with pytest.raises(InsufficientCreditsError):
        await consume_credit(
            db_session,
            user_id=user.id,
            credit_kind=CreditKind.free,
            reason="resume_build",
        )

    assert await _count_credit_rows(db_session, user.id) == 0
    await db_session.refresh(user)
    assert user.credit_balance == 0


@pytest.mark.integration
async def test_consume_credit_for_unknown_user_fails_closed(
    db_session: AsyncSession,
) -> None:
    """A missing user row must deny, not default to "allowed".

    ``consume_credit`` locks the user row first; a ``None`` there means
    the account vanished mid-request (closure, hard delete). Treating
    that absence as a zero-cost success would hand a deleted account
    unlimited free work.
    """
    with pytest.raises(InsufficientCreditsError):
        await consume_credit(
            db_session,
            user_id=uuid.uuid4(),
            credit_kind=CreditKind.free,
            reason="resume_build",
        )


# ---------------------------------------------------------------------------
# 3. Empty results must not bypass the access check
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_version_restore_rejects_a_snapshot_from_another_session(
    app_client: AsyncClient,
) -> None:
    """Restore must resolve the snapshot *within* the named session.

    ``POST /api/sessions/{session_id}/resume/versions/{snapshot_id}/restore``
    takes two identifiers. If the snapshot were resolved globally by id,
    the session in the path would become decorative and any caller could
    pull another session's tailored résumé into their own. The empty
    result for a foreign snapshot must be a 404, not a fallback to
    "whatever that id refers to".
    """
    from app.routers.phases import _append_version_snapshot

    donor = await create_session()
    tailored = TailoredResumeOutput(
        summary="Donor summary that must not leak across sessions.",
        skills=["donor-only-skill"],
    )
    snapshot = _append_version_snapshot(donor, label="v1", output=tailored)
    await update_session(donor)

    borrower = await create_session()

    response = await app_client.post(
        f"/api/sessions/{borrower.session_id}/resume/versions/"
        f"{snapshot.snapshot_id}/restore"
    )
    assert response.status_code == 404, response.text
    assert "Donor summary" not in response.text

    refreshed = await get_session(borrower.session_id)
    assert refreshed is not None
    assert refreshed.phase3_output is None, (
        "a rejected restore must not write the foreign snapshot into the "
        "target session"
    )

    # Positive control: the donor can restore its own snapshot, so the
    # 404 above means "not yours" rather than "snapshot never persisted".
    own = await app_client.post(
        f"/api/sessions/{donor.session_id}/resume/versions/"
        f"{snapshot.snapshot_id}/restore"
    )
    assert own.status_code == 200, own.text


@pytest.mark.integration
async def test_missing_resume_record_returns_404_rather_than_someone_elses(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """An empty owner-scoped lookup must stay empty.

    The tempting "nothing found, widen the query" branch is what turns a
    404 into a cross-tenant read. Two users share one session id here, so
    a lookup that dropped the ``user_id`` predicate on the empty path
    would return the other user's row instead of 404.
    """
    from app.services.auth.tokens import create_access_token

    owner = await _seed_user(db_session, email=f"owner-{uuid.uuid4().hex[:8]}@example.com")
    stranger = await _seed_user(
        db_session, email=f"stranger-{uuid.uuid4().hex[:8]}@example.com"
    )
    shared_session_id = f"sess-{uuid.uuid4().hex[:12]}"

    db_session.add(
        ResumeRecord(
            id=uuid.uuid4(),
            user_id=owner.id,
            session_id=shared_session_id,
            jd_title="Principal Engineer",
            jd_company="Helio Robotics",
            jd_text_hash=uuid.uuid4().hex,
            tags=[],
            current_ats_score=88,
            starting_ats_score=80,
            status=ResumeRecordStatus.draft,
        )
    )
    await db_session.commit()

    stranger_token = create_access_token(stranger.id)
    response = await app_client.get(
        f"/api/sessions/{shared_session_id}/resume-record",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert response.status_code == 404, response.text
    assert "Helio Robotics" not in response.text


# ---------------------------------------------------------------------------
# 4. Configuration that can silently disable a control
# ---------------------------------------------------------------------------


def test_quota_enforcement_is_on_by_default_in_production_grade_envs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without an explicit override, production-grade envs enforce quota."""
    monkeypatch.setattr(settings, "BILLING_SKIP_QUOTA", None)
    for env in ("ci", "staging", "production"):
        monkeypatch.setattr(settings, "APP_ENV", env)
        assert should_skip_billing_quota() is False, (
            f"APP_ENV={env} must enforce billing quota by default"
        )


@pytest.mark.parametrize("env", ["ci", "staging", "production"])
def test_quota_enforcement_cannot_be_disabled_in_production(
    monkeypatch: pytest.MonkeyPatch,
    env: str,
) -> None:
    """``BILLING_SKIP_QUOTA`` is a local-dev convenience only — ignored in production-grade envs."""
    monkeypatch.setattr(settings, "BILLING_SKIP_QUOTA", True)
    monkeypatch.setattr(settings, "APP_ENV", env)
    assert should_skip_billing_quota() is False
