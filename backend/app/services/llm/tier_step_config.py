"""Admin tier step LLM pins — load and cache refresh."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.model_registry import STEP_DEFAULTS, PipelineStep
from app.llm.tier_step_pin_cache import set_tier_step_pins
from app.models.tier_step_llm_config import TierStepLLMConfig

log = structlog.get_logger()


def _coerce_step(step: str) -> PipelineStep:
    if step not in STEP_DEFAULTS:
        raise ValueError(f"unknown_pipeline_step:{step}")
    return step  # type: ignore[return-value]


async def load_active_tier_step_pins(session: AsyncSession) -> int:
    """Load active DB tier pins into the in-process cache. Returns pin count."""
    rows = (
        await session.execute(
            select(TierStepLLMConfig).where(TierStepLLMConfig.is_active.is_(True))
        )
    ).scalars().all()
    pins: dict[tuple[str, PipelineStep], tuple[str, str]] = {}
    for row in rows:
        try:
            step = _coerce_step(row.step)
        except ValueError:
            log.warning(
                "tier_step_llm_config.unknown_step_skipped",
                plan_code=row.plan_code,
                step=row.step,
                config_id=str(row.id),
            )
            continue
        pins[(row.plan_code, step)] = (row.provider.value, row.model_string)
    set_tier_step_pins(pins)
    log.info("tier_step_llm_config.cache_loaded", active_pins=len(pins))
    return len(pins)


async def refresh_tier_step_pin_cache(session: AsyncSession) -> int:
    """Reload tier pin cache after an admin write."""
    return await load_active_tier_step_pins(session)


__all__ = [
    "load_active_tier_step_pins",
    "refresh_tier_step_pin_cache",
]
