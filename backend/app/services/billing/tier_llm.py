"""Phase 3 LLM routing — delegates to the step registry (M18)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.model_registry import resolve_model
from app.models.user import User
from app.services.llm.plan_code_for_llm import resolve_plan_code_for_llm


async def resolve_phase3_model_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> tuple[str, str]:
    """Return ``(provider, model)`` for Phase 3 from the unified step map."""
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    plan_code = await resolve_plan_code_for_llm(session, user)
    return resolve_model("phase3_rewrite", plan_code=plan_code)


__all__ = ["resolve_phase3_model_for_user"]
