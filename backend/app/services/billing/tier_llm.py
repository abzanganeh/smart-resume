"""Phase 3 LLM routing — delegates to the step registry (M18)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.model_registry import resolve_model


async def resolve_phase3_model_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> tuple[str, str]:
    """Return ``(provider, model)`` for Phase 3 from the unified step map."""
    _ = (session, user_id)
    return resolve_model("phase3_rewrite")


__all__ = ["resolve_phase3_model_for_user"]
