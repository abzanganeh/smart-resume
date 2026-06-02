"""Credit / subscription routing tree per SYSTEM_DESIGN_PHASE_2 §18.3.

```
Request arrives
  └─ Is user suspended? → HTTP 403 account_suspended
  └─ Is the action a paid action?
       └─ NO  → run; no decrement
       └─ YES → Is the user subscribed and within plan limits?
                  ├─ YES → run; increment the right period counter
                  └─ NO  → Is action allowed on free credits AND credits ≥ cost?
                            ├─ YES → decrement credits; run
                            └─ NO  → HTTP 402 with upgrade JSON
```

This module does **not** call any LLM; it only commits the quota
accounting (counter increment for subscribers, ledger decrement for
free-credit consumers).  Callers wrap their LLM dispatch around it.

Action labels are stable strings the rest of the codebase passes in:

- ``resume_build``      — Agent Phases 1–4 full run
- ``ats_recalc``        — Phase 4 only against an existing tailored resume
- ``cover_letter``      — §18.11
- ``section_regen``     — §18.5 per-section / per-bullet regen
- ``job_search``        — RP3 search counter
- ``fit_analysis``      — RP3 fit analysis (subscription-only)
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    CreditKind,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.user import User
from app.services.billing.credits import consume_credit
from app.services.billing.exceptions import (
    AccountSuspendedError,
    InsufficientCreditsError,
    PlanLimitReachedError,
    SubscriptionRequiredError,
)

log = structlog.get_logger("billing.quota")


# §18.3 plan tier limits — keep in sync with the canonical tier table.
PLAN_RESUMES_PER_PERIOD: dict[SubscriptionPlan, int] = {
    SubscriptionPlan.daily: 40,
    SubscriptionPlan.weekly: 280,
    SubscriptionPlan.monthly: 150,
}
PLAN_SEARCHES_PER_PERIOD: dict[SubscriptionPlan, int] = {
    SubscriptionPlan.daily: 10,
    SubscriptionPlan.weekly: 70,
    SubscriptionPlan.monthly: 300,
}


class QuotaAction(str, enum.Enum):
    resume_build = "resume_build"
    ats_recalc = "ats_recalc"
    cover_letter = "cover_letter"
    section_regen = "section_regen"
    job_search = "job_search"
    fit_analysis = "fit_analysis"
    story_build = "story_build"


# Actions that may be paid by *free* tier credits (§18.3 table).  Job
# search / fit analysis are subscription-only.
FREE_CREDIT_ACTIONS: frozenset[QuotaAction] = frozenset(
    {
        QuotaAction.resume_build,
        QuotaAction.ats_recalc,
        QuotaAction.cover_letter,
        QuotaAction.section_regen,
        QuotaAction.story_build,
    }
)
# Actions that count against the resume counter (§18.3 "Resumes / period").
# ``cover_letter`` is bundled for subscribers — see
# :func:`check_quota_for_cover_letter`.
RESUME_COUNTER_ACTIONS: frozenset[QuotaAction] = frozenset(
    {
        QuotaAction.resume_build,
        QuotaAction.ats_recalc,
        QuotaAction.section_regen,
    }
)
# Actions that count against the search counter.
SEARCH_COUNTER_ACTIONS: frozenset[QuotaAction] = frozenset(
    {QuotaAction.job_search, QuotaAction.fit_analysis}
)


@dataclass(frozen=True, slots=True)
class QuotaDecision:
    """Result of the routing tree.

    - ``charged_to`` describes the accounting row that was bumped
      ("subscription_resume", "subscription_search", "free_credit").
    - ``subscription_id`` is set whenever a counter on a Subscription
      was incremented.
    - ``credit_transaction_id`` is set whenever a free-tier credit row
      was inserted.
    """

    action: QuotaAction
    charged_to: str
    subscription_id: Optional[uuid.UUID] = None
    credit_transaction_id: Optional[uuid.UUID] = None


async def _active_subscription_for(
    session: AsyncSession, *, user_id: uuid.UUID
) -> Subscription | None:
    """Return the user's currently entitled subscription, or None.

    "Entitled" mirrors §7.7: status ∈ {active, trialing, grace,
    cancel_at_period_end}.  Paused / expired don't count.
    """
    stmt = (
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .where(
            Subscription.status.in_(
                [
                    SubscriptionStatus.active,
                    SubscriptionStatus.trialing,
                    SubscriptionStatus.grace,
                    SubscriptionStatus.cancel_at_period_end,
                ]
            )
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _within_period(sub: Subscription, *, now: datetime) -> bool:
    return sub.period_start <= now <= sub.period_end


async def check_and_increment_quota(
    session: AsyncSession,
    *,
    user: User,
    action: QuotaAction,
    session_id: str | None = None,
) -> QuotaDecision:
    """Run the routing tree and persist the side-effect.

    Raises one of:
    - :class:`AccountSuspendedError` (HTTP 403)
    - :class:`SubscriptionRequiredError` (HTTP 402 — subscription gate
      for job_search / fit_analysis)
    - :class:`PlanLimitReachedError` (HTTP 402 — plan counter exhausted)
    - :class:`InsufficientCreditsError` (HTTP 402 — out of free credits)

    Otherwise returns a :class:`QuotaDecision` describing what was
    debited.  The caller commits the surrounding transaction; on
    failure further down the pipeline the entire run is rolled back so
    the counter / credit is not lost.
    """
    if user.is_suspended:
        raise AccountSuspendedError("account_suspended")

    now = datetime.now(timezone.utc)
    sub = await _active_subscription_for(session, user_id=user.id)

    # Try the subscription path first when a subscription exists.
    if sub is not None and _within_period(sub, now=now):
        if sub.status == SubscriptionStatus.paused:
            # Defensive — _active_subscription_for filters paused, but
            # be explicit so future refactors don't regress this.
            sub = None

    if sub is not None and _within_period(sub, now=now):
        if action in RESUME_COUNTER_ACTIONS:
            limit = PLAN_RESUMES_PER_PERIOD[sub.plan]
            if sub.resumes_used >= limit:
                # Fall through to the free-credit branch only when the
                # action is also free-credit-eligible; otherwise raise.
                if action not in FREE_CREDIT_ACTIONS:
                    raise PlanLimitReachedError(action.value, sub.resumes_used, limit)
            else:
                sub.resumes_used += 1
                await session.flush()
                return QuotaDecision(
                    action=action,
                    charged_to="subscription_resume",
                    subscription_id=sub.id,
                )
        elif action in SEARCH_COUNTER_ACTIONS:
            limit = PLAN_SEARCHES_PER_PERIOD[sub.plan]
            if sub.searches_used >= limit:
                raise PlanLimitReachedError(action.value, sub.searches_used, limit)
            sub.searches_used += 1
            await session.flush()
            return QuotaDecision(
                action=action,
                charged_to="subscription_search",
                subscription_id=sub.id,
            )

    # Free-credit fallback.  Subscription-only actions cannot be paid
    # for with free credits — emit a 402 ``subscription_required`` so
    # the upgrade JSON gets surfaced to the UI.
    if action not in FREE_CREDIT_ACTIONS:
        raise SubscriptionRequiredError(action.value)

    try:
        row = await consume_credit(
            session,
            user_id=user.id,
            credit_kind=CreditKind.free,
            reason=action.value,
            session_id=session_id,
        )
    except InsufficientCreditsError:
        raise

    return QuotaDecision(
        action=action,
        charged_to="free_credit",
        credit_transaction_id=row.id,
    )


async def check_quota_for_cover_letter(
    session: AsyncSession,
    *,
    user: User,
    session_id: str | None = None,
) -> QuotaDecision:
    """Quota for cover letter generation (§18.11).

    Subscribers run cover letter generation without incrementing
    ``resumes_used``.  Free users consume one ``cover_letter`` credit.
    """
    if user.is_suspended:
        raise AccountSuspendedError("account_suspended")

    now = datetime.now(timezone.utc)
    sub = await _active_subscription_for(session, user_id=user.id)

    if sub is not None and _within_period(sub, now=now):
        if sub.status != SubscriptionStatus.paused:
            return QuotaDecision(
                action=QuotaAction.cover_letter,
                charged_to="subscription_cover_letter",
                subscription_id=sub.id,
            )

    try:
        row = await consume_credit(
            session,
            user_id=user.id,
            credit_kind=CreditKind.free,
            reason=QuotaAction.cover_letter.value,
            session_id=session_id,
        )
    except InsufficientCreditsError:
        raise

    return QuotaDecision(
        action=QuotaAction.cover_letter,
        charged_to="free_credit",
        credit_transaction_id=row.id,
    )


async def check_quota_for_section_regen(
    session: AsyncSession,
    *,
    user: User,
    session_id: str | None = None,
) -> QuotaDecision:
    """Quota for scoped Phase 3 section/bullet regen (§18.5).

    Subscribers run scoped regen without incrementing ``resumes_used``.
    Free users consume one ``section_regen`` credit.
    """
    if user.is_suspended:
        raise AccountSuspendedError("account_suspended")

    now = datetime.now(timezone.utc)
    sub = await _active_subscription_for(session, user_id=user.id)

    if sub is not None and _within_period(sub, now=now):
        if sub.status != SubscriptionStatus.paused:
            return QuotaDecision(
                action=QuotaAction.section_regen,
                charged_to="subscription_section_regen",
                subscription_id=sub.id,
            )

    try:
        row = await consume_credit(
            session,
            user_id=user.id,
            credit_kind=CreditKind.free,
            reason=QuotaAction.section_regen.value,
            session_id=session_id,
        )
    except InsufficientCreditsError:
        raise

    return QuotaDecision(
        action=QuotaAction.section_regen,
        charged_to="free_credit",
        credit_transaction_id=row.id,
    )


async def check_quota_for_story(
    session: AsyncSession,
    *,
    user: User,
    whisper_path: bool,
    byok_active: bool,
    session_id: str | None = None,
) -> QuotaDecision:
    """Quota for story-mode resume generation.

    Credit cost:
      - BYOK (any browser):           0 credits — user pays their own LLM costs
      - Platform LLM + Web Speech:    0 credits — transcription is browser-native; LLM cost ~$0.001
      - Platform LLM + Whisper:       2 credits — Whisper transcription costs ~$0.12 for 20 min

    Subscribers always pay 0 credits for story builds (subscription covers usage).
    """
    if user.is_suspended:
        raise AccountSuspendedError("account_suspended")

    # BYOK users: always free
    if byok_active:
        return QuotaDecision(
            action=QuotaAction.story_build,
            charged_to="byok",
        )

    # Subscribers: free within subscription
    sub = await _active_subscription_for(session, user_id=user.id)
    now = datetime.now(timezone.utc)
    if sub is not None and _within_period(sub, now=now) and sub.status != SubscriptionStatus.paused:
        return QuotaDecision(
            action=QuotaAction.story_build,
            charged_to="subscription",
            subscription_id=sub.id,
        )

    # Web Speech path: free for free users
    if not whisper_path:
        return QuotaDecision(
            action=QuotaAction.story_build,
            charged_to="free_web_speech",
        )

    # Whisper path: costs 2 credits — consume_credit deducts 1 at a time, so call twice
    WHISPER_CREDIT_COST = 2
    last_row = None
    for _ in range(WHISPER_CREDIT_COST):
        try:
            last_row = await consume_credit(
                session,
                user_id=user.id,
                credit_kind=CreditKind.free,
                reason=QuotaAction.story_build.value,
                session_id=session_id,
            )
        except InsufficientCreditsError:
            raise

    return QuotaDecision(
        action=QuotaAction.story_build,
        charged_to="free_credit",
        credit_transaction_id=last_row.id if last_row else None,
    )


__all__ = [
    "FREE_CREDIT_ACTIONS",
    "PLAN_RESUMES_PER_PERIOD",
    "PLAN_SEARCHES_PER_PERIOD",
    "QuotaAction",
    "QuotaDecision",
    "RESUME_COUNTER_ACTIONS",
    "SEARCH_COUNTER_ACTIONS",
    "check_and_increment_quota",
    "check_quota_for_cover_letter",
    "check_quota_for_section_regen",
    "check_quota_for_story",
]
