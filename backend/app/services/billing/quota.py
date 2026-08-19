"""Credit / subscription routing tree per SYSTEM_DESIGN_PHASE_2 §18.3.

Limits are loaded from ``tier_limits_config`` (admin-configurable) via
:mod:`tier_limits_lookup`; legacy hard-coded plan tables are removed.
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

from app.models.billing import CreditKind, Subscription, SubscriptionStatus
from app.models.user import User, CreditTransaction
from app.services.admin.feature_unlocks import user_has_feature_unlock
from app.services.billing.credits import consume_credit, record_quota_audit
from app.services.billing.exceptions import (
    AccountSuspendedError,
    InsufficientCreditsError,
    PlanLimitReachedError,
    SubscriptionRequiredError,
)
from app.services.billing.plan_code_resolver import resolve_plan_code_for_user
from app.services.billing.tier_limits_lookup import TierLimits, get_active_tier_limits

log = structlog.get_logger("billing.quota")


class QuotaAction(str, enum.Enum):
    resume_build = "resume_build"
    ats_recalc = "ats_recalc"
    cover_letter = "cover_letter"
    section_regen = "section_regen"
    job_search = "job_search"
    fit_analysis = "fit_analysis"
    story_build = "story_build"
    story_build_generate = "story_build_generate"
    story_build_save = "story_build_save"
    story_coach = "story_coach"
    story_interview = "story_interview"


FREE_CREDIT_ACTIONS: frozenset[QuotaAction] = frozenset(
    {
        QuotaAction.resume_build,
        QuotaAction.ats_recalc,
        QuotaAction.cover_letter,
        QuotaAction.section_regen,
        QuotaAction.story_build,
        QuotaAction.story_build_generate,
        QuotaAction.story_build_save,
        QuotaAction.story_coach,
        QuotaAction.story_interview,
    }
)
RESUME_COUNTER_ACTIONS: frozenset[QuotaAction] = frozenset(
    {
        QuotaAction.resume_build,
        QuotaAction.ats_recalc,
        QuotaAction.section_regen,
    }
)
SEARCH_COUNTER_ACTIONS: frozenset[QuotaAction] = frozenset({QuotaAction.job_search})
FIT_COUNTER_ACTIONS: frozenset[QuotaAction] = frozenset({QuotaAction.fit_analysis})


@dataclass(frozen=True, slots=True)
class QuotaDecision:
    action: QuotaAction
    charged_to: str
    subscription_id: Optional[uuid.UUID] = None
    credit_transaction_id: Optional[uuid.UUID] = None


async def _active_subscription_for(
    session: AsyncSession, *, user_id: uuid.UUID
) -> Subscription | None:
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


async def _tier_limits_for_user(
    session: AsyncSession, user: User
) -> TierLimits:
    plan_code = await resolve_plan_code_for_user(session, user)
    return await get_active_tier_limits(session, plan_code)


async def check_and_increment_quota(
    session: AsyncSession,
    *,
    user: User,
    action: QuotaAction,
    session_id: str | None = None,
) -> QuotaDecision:
    if user.is_suspended:
        raise AccountSuspendedError("account_suspended")

    now = datetime.now(timezone.utc)
    sub = await _active_subscription_for(session, user_id=user.id)

    if sub is not None and _within_period(sub, now=now):
        if sub.status == SubscriptionStatus.paused:
            sub = None

    if sub is not None and _within_period(sub, now=now):
        limits = await _tier_limits_for_user(session, user)

        if action in RESUME_COUNTER_ACTIONS:
            limit = limits.resumes_per_period
            if sub.resumes_used >= limit:
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
            limit = limits.searches_per_period
            if sub.searches_used >= limit:
                raise PlanLimitReachedError(action.value, sub.searches_used, limit)
            sub.searches_used += 1
            await session.flush()
            return QuotaDecision(
                action=action,
                charged_to="subscription_search",
                subscription_id=sub.id,
            )
        elif action in FIT_COUNTER_ACTIONS:
            limit = limits.fit_analyses_per_period
            if sub.fit_analyses_used >= limit:
                raise PlanLimitReachedError(
                    action.value, sub.fit_analyses_used, limit
                )
            sub.fit_analyses_used += 1
            await session.flush()
            return QuotaDecision(
                action=action,
                charged_to="subscription_fit",
                subscription_id=sub.id,
            )

    if action not in FREE_CREDIT_ACTIONS:
        if action == QuotaAction.job_search and await user_has_feature_unlock(
            session, user_id=user.id, feature="job_search", now=now
        ):
            return QuotaDecision(
                action=action,
                charged_to="feature_unlock_job_search",
            )
        if action == QuotaAction.fit_analysis and await user_has_feature_unlock(
            session, user_id=user.id, feature="fit_analysis", now=now
        ):
            return QuotaDecision(
                action=action,
                charged_to="feature_unlock_fit_analysis",
            )
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


async def _user_has_story_quota_event(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    reason: str,
) -> bool:
    row = await session.execute(
        select(CreditTransaction.id)
        .where(CreditTransaction.user_id == user_id)
        .where(CreditTransaction.reason == reason)
        .limit(1)
    )
    return row.scalar_one_or_none() is not None


async def _subscriber_story_decision(
    session: AsyncSession,
    *,
    user: User,
    action: QuotaAction,
) -> QuotaDecision | None:
    sub = await _active_subscription_for(session, user_id=user.id)
    now = datetime.now(timezone.utc)
    if sub is not None and _within_period(sub, now=now) and sub.status != SubscriptionStatus.paused:
        return QuotaDecision(
            action=action,
            charged_to="subscription",
            subscription_id=sub.id,
        )
    return None


async def check_quota_for_story_generate(
    session: AsyncSession,
    *,
    user: User,
    whisper_path: bool,
    session_id: str | None = None,
) -> QuotaDecision:
    """Quota for generating a story resume draft (preview, not saved yet).

    First generate per account is free; each later generate costs 1 credit.
    Subscribers are always free. Whisper path still uses whisper_gate.
    """
    if user.is_suspended:
        raise AccountSuspendedError("account_suspended")

    if whisper_path:
        from app.services.billing.whisper_gate import check_and_increment_whisper_use

        await check_and_increment_whisper_use(session, user=user)

    sub_decision = await _subscriber_story_decision(
        session, user=user, action=QuotaAction.story_build_generate
    )
    if sub_decision is not None:
        return sub_decision

    reason = QuotaAction.story_build_generate.value
    if not await _user_has_story_quota_event(session, user_id=user.id, reason=reason):
        await record_quota_audit(
            session,
            user_id=user.id,
            reason=reason,
            session_id=session_id,
        )
        return QuotaDecision(
            action=QuotaAction.story_build_generate,
            charged_to="first_story_generate",
        )

    try:
        row = await consume_credit(
            session,
            user_id=user.id,
            credit_kind=CreditKind.free,
            reason=reason,
            session_id=session_id,
        )
    except InsufficientCreditsError:
        raise

    return QuotaDecision(
        action=QuotaAction.story_build_generate,
        charged_to="free_credit",
        credit_transaction_id=row.id,
    )


async def check_quota_for_story_save(
    session: AsyncSession,
    *,
    user: User,
    session_id: str | None = None,
) -> QuotaDecision:
    """Quota for saving a reviewed story resume to the master profile.

    First save per account is free; each later save costs 1 credit.
    Subscribers are always free.
    """
    if user.is_suspended:
        raise AccountSuspendedError("account_suspended")

    sub_decision = await _subscriber_story_decision(
        session, user=user, action=QuotaAction.story_build_save
    )
    if sub_decision is not None:
        return sub_decision

    reason = QuotaAction.story_build_save.value
    if not await _user_has_story_quota_event(session, user_id=user.id, reason=reason):
        await record_quota_audit(
            session,
            user_id=user.id,
            reason=reason,
            session_id=session_id,
        )
        return QuotaDecision(
            action=QuotaAction.story_build_save,
            charged_to="first_story_save",
        )

    try:
        row = await consume_credit(
            session,
            user_id=user.id,
            credit_kind=CreditKind.free,
            reason=reason,
            session_id=session_id,
        )
    except InsufficientCreditsError:
        raise

    return QuotaDecision(
        action=QuotaAction.story_build_save,
        charged_to="free_credit",
        credit_transaction_id=row.id,
    )


async def check_quota_for_story(
    session: AsyncSession,
    *,
    user: User,
    whisper_path: bool,
    session_id: str | None = None,
) -> QuotaDecision:
    """Legacy alias — story preview generation quota."""
    return await check_quota_for_story_generate(
        session,
        user=user,
        whisper_path=whisper_path,
        session_id=session_id,
    )


async def _story_coach_build_already_charged(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    story_session_id: str,
) -> bool:
    if not story_session_id.strip():
        return False
    row = await session.execute(
        select(CreditTransaction.id)
        .where(CreditTransaction.user_id == user_id)
        .where(CreditTransaction.reason == QuotaAction.story_coach.value)
        .where(CreditTransaction.session_id == story_session_id)
        .where(CreditTransaction.delta < 0)
        .limit(1)
    )
    return row.scalar_one_or_none() is not None


async def check_quota_for_story_coach(
    session: AsyncSession,
    *,
    user: User,
    session_id: str | None = None,
) -> QuotaDecision:
    if user.is_suspended:
        raise AccountSuspendedError("account_suspended")

    now = datetime.now(timezone.utc)
    sub = await _active_subscription_for(session, user_id=user.id)
    if sub is not None and _within_period(sub, now=now) and sub.status != SubscriptionStatus.paused:
        return QuotaDecision(
            action=QuotaAction.story_coach,
            charged_to="subscription",
            subscription_id=sub.id,
        )

    if session_id and await _story_coach_build_already_charged(
        session, user_id=user.id, story_session_id=session_id
    ):
        return QuotaDecision(
            action=QuotaAction.story_coach,
            charged_to="story_build_session_included",
        )

    try:
        row = await consume_credit(
            session,
            user_id=user.id,
            credit_kind=CreditKind.free,
            reason=QuotaAction.story_coach.value,
            session_id=session_id,
        )
    except InsufficientCreditsError:
        raise

    return QuotaDecision(
        action=QuotaAction.story_coach,
        charged_to="free_credit",
        credit_transaction_id=row.id,
    )


async def check_quota_for_story_interview(
    session: AsyncSession,
    *,
    user: User,
    session_id: str | None = None,
) -> QuotaDecision:
    if user.is_suspended:
        raise AccountSuspendedError("account_suspended")

    now = datetime.now(timezone.utc)
    sub = await _active_subscription_for(session, user_id=user.id)
    if sub is not None and _within_period(sub, now=now) and sub.status != SubscriptionStatus.paused:
        return QuotaDecision(
            action=QuotaAction.story_interview,
            charged_to="subscription",
            subscription_id=sub.id,
        )

    try:
        row = await consume_credit(
            session,
            user_id=user.id,
            credit_kind=CreditKind.free,
            reason=QuotaAction.story_interview.value,
            session_id=session_id,
        )
    except InsufficientCreditsError:
        raise

    return QuotaDecision(
        action=QuotaAction.story_interview,
        charged_to="free_credit",
        credit_transaction_id=row.id,
    )


__all__ = [
    "FIT_COUNTER_ACTIONS",
    "FREE_CREDIT_ACTIONS",
    "QuotaAction",
    "QuotaDecision",
    "RESUME_COUNTER_ACTIONS",
    "SEARCH_COUNTER_ACTIONS",
    "check_and_increment_quota",
    "check_quota_for_cover_letter",
    "check_quota_for_section_regen",
    "check_quota_for_story",
    "check_quota_for_story_generate",
    "check_quota_for_story_save",
    "check_quota_for_story_coach",
    "check_quota_for_story_interview",
]
