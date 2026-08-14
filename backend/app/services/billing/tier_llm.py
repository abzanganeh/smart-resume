"""Phase 3 LLM routing from ``tier_limits_config`` (pricing restructure 2026-08)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tier_limits import TierLimitsConfig
from app.models.user import User
from app.services.billing.plan_code_resolver import resolve_plan_code_for_user
from app.services.billing.tier_limits import seed_row_for_plan


async def resolve_phase3_model_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> tuple[str, str]:
    """Return ``(provider, model)`` from the user's effective tier limits row."""
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one()
    plan_code = await resolve_plan_code_for_user(session, user)
    stmt = (
        select(TierLimitsConfig)
        .where(TierLimitsConfig.plan_code == plan_code)
        .where(TierLimitsConfig.is_active.is_(True))
        .order_by(TierLimitsConfig.created_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return row.llm_provider, row.llm_model_phase3
    seed = seed_row_for_plan(plan_code) or seed_row_for_plan("free")
    assert seed is not None
    return seed["llm_provider"], seed["llm_model_phase3"]


__all__ = ["resolve_phase3_model_for_user"]
