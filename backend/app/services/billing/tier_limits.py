"""Tier limits seed data and lookup helpers.

Canonical limits for the pricing restructure (2026-08).  Migration
``0020_tier_limits_config`` inserts these rows; admin can override via
``tier_limits_config`` table later.
"""

from __future__ import annotations

from typing import Any, TypedDict


class TierLimitsSeedRow(TypedDict):
    plan_code: str
    resumes_per_period: int
    cover_letters_per_period: int
    searches_per_period: int
    fit_analyses_per_period: int
    checkups_per_period: int | None
    story_sessions: int | None
    coached_sessions: int | None
    career_watch_companies: int
    career_watch_interval_minutes: int
    tracker_active_limit: int | None
    whisper_enabled: bool
    whisper_uses_per_period: int | None
    llm_provider: str
    llm_model_phase3: str
    soft_cap_message: str | None


CANONICAL_PLAN_CODES: frozenset[str] = frozenset(
    {
        "free",
        "weekly",
        "monthly_pro",
        "yearly_pro",
        "monthly_plus",
        "yearly_plus",
        "monthly_premium",
        "yearly_premium",
    }
)

_SOFT_CAP_MSG = (
    "You have reached the fair-use limit for this billing period. "
    "Contact support if you need a temporary increase."
)


def _paid_tier(
    *,
    plan_code: str,
    resumes: int,
    searches: int,
    fit: int,
    checkups: int | None,
    career_companies: int,
    career_interval: int,
    tracker: int | None,
    whisper_uses: int | None,
    llm_provider: str,
    llm_model: str,
    soft_cap: bool = False,
) -> TierLimitsSeedRow:
    return TierLimitsSeedRow(
        plan_code=plan_code,
        resumes_per_period=resumes,
        cover_letters_per_period=resumes,
        searches_per_period=searches,
        fit_analyses_per_period=fit,
        checkups_per_period=checkups,
        story_sessions=None,
        coached_sessions=None,
        career_watch_companies=career_companies,
        career_watch_interval_minutes=career_interval,
        tracker_active_limit=tracker,
        whisper_enabled=whisper_uses is None or (whisper_uses is not None and whisper_uses > 0),
        whisper_uses_per_period=whisper_uses,
        llm_provider=llm_provider,
        llm_model_phase3=llm_model,
        soft_cap_message=_SOFT_CAP_MSG if soft_cap else None,
    )


def get_seed_rows() -> list[TierLimitsSeedRow]:
    """Return default tier limit rows for all canonical plan codes."""
    return [
        TierLimitsSeedRow(
            plan_code="free",
            # 2026-08-19: raised free resumes_per_period 3 -> 6.  This is the
            # registration grant credit count; free users must still stay
            # under tracker_active_limit which caps how many rows they can
            # keep in the tracker at once.
            resumes_per_period=6,
            cover_letters_per_period=6,
            searches_per_period=5,
            fit_analyses_per_period=3,
            checkups_per_period=3,
            story_sessions=1,
            coached_sessions=1,
            career_watch_companies=1,
            career_watch_interval_minutes=30,
            tracker_active_limit=10,
            whisper_enabled=False,
            whisper_uses_per_period=0,
            llm_provider="gemini",
            llm_model_phase3="gemini-3.5-flash-lite",
            soft_cap_message=None,
        ),
        _paid_tier(
            plan_code="weekly",
            resumes=10,
            searches=20,
            fit=10,
            checkups=10,
            career_companies=3,
            career_interval=15,
            tracker=30,
            whisper_uses=2,
            llm_provider="gemini",
            llm_model="gemini-3.5-flash",
        ),
        _paid_tier(
            plan_code="monthly_pro",
            resumes=50,
            searches=100,
            fit=50,
            checkups=None,
            career_companies=10,
            career_interval=15,
            tracker=None,
            whisper_uses=5,
            llm_provider="gemini",
            llm_model="gemini-3.5-flash",
        ),
        _paid_tier(
            plan_code="yearly_pro",
            resumes=50,
            searches=100,
            fit=50,
            checkups=None,
            career_companies=10,
            career_interval=15,
            tracker=None,
            whisper_uses=5,
            llm_provider="gemini",
            llm_model="gemini-3.5-flash",
        ),
        _paid_tier(
            plan_code="monthly_plus",
            resumes=100,
            searches=200,
            fit=100,
            checkups=None,
            career_companies=30,
            career_interval=5,
            tracker=None,
            whisper_uses=15,
            llm_provider="gemini",
            llm_model="gemini-3.5-flash",
        ),
        _paid_tier(
            plan_code="yearly_plus",
            resumes=100,
            searches=200,
            fit=100,
            checkups=None,
            career_companies=30,
            career_interval=5,
            tracker=None,
            whisper_uses=15,
            llm_provider="gemini",
            llm_model="gemini-3.5-flash",
        ),
        _paid_tier(
            plan_code="monthly_premium",
            resumes=300,
            searches=300,
            fit=300,
            checkups=None,
            career_companies=50,
            career_interval=5,
            # 2026-08-19: premium is "unlimited" only in marketing copy —
            # it has always carried a fair-use soft cap.  Anchor the tracker
            # limit at 250 (roughly 2x pro / plus) so a runaway integration
            # can't silently rack up thousands of tracker rows.
            tracker=250,
            whisper_uses=None,
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-6",
            soft_cap=True,
        ),
        _paid_tier(
            plan_code="yearly_premium",
            resumes=300,
            searches=300,
            fit=300,
            checkups=None,
            career_companies=50,
            career_interval=5,
            tracker=250,
            whisper_uses=None,
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-6",
            soft_cap=True,
        ),
    ]


def seed_row_for_plan(plan_code: str) -> TierLimitsSeedRow | None:
    for row in get_seed_rows():
        if row["plan_code"] == plan_code:
            return row
    return None


__all__ = [
    "CANONICAL_PLAN_CODES",
    "TierLimitsSeedRow",
    "get_seed_rows",
    "seed_row_for_plan",
]
