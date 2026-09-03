"""Resolve server-side plan_code for LLM routing (never from request body)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.billing.plan_code_resolver import resolve_plan_code_for_user


async def resolve_plan_code_for_llm(
    db: AsyncSession,
    user: User | None,
) -> str:
    """Return canonical plan_code for LLM routing; anonymous users route as ``free``."""
    if user is None:
        return "free"
    return await resolve_plan_code_for_user(db, user)


async def resolve_plan_code_for_llm_user_id(
    db: AsyncSession,
    user_id: uuid.UUID | None,
) -> str:
    """Resolve plan_code from a user id (or ``free`` when absent/unknown)."""
    if user_id is None:
        return "free"
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    return await resolve_plan_code_for_llm(db, user)


__all__ = [
    "resolve_plan_code_for_llm",
    "resolve_plan_code_for_llm_user_id",
]
