"""Admin step LLM pins — seed, load, and cache refresh."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.model_registry import STEP_DEFAULTS, PipelineStep
from app.llm.step_pin_cache import set_step_pins
from app.models.llm_config import LLMProvider
from app.models.step_llm_config import StepLLMConfig

log = structlog.get_logger()


def _coerce_step(step: str) -> PipelineStep:
    if step not in STEP_DEFAULTS:
        raise ValueError(f"unknown_pipeline_step:{step}")
    return step  # type: ignore[return-value]


async def load_active_step_pins(session: AsyncSession) -> int:
    """Load active DB pins into the in-process cache. Returns pin count."""
    rows = (
        await session.execute(
            select(StepLLMConfig).where(StepLLMConfig.is_active.is_(True))
        )
    ).scalars().all()
    pins: dict[PipelineStep, tuple[str, str]] = {}
    for row in rows:
        try:
            step = _coerce_step(row.step)
        except ValueError:
            log.warning(
                "step_llm_config.unknown_step_skipped",
                step=row.step,
                config_id=str(row.id),
            )
            continue
        pins[step] = (row.provider.value, row.model_string)
    set_step_pins(pins)
    log.info("step_llm_config.cache_loaded", active_pins=len(pins))
    return len(pins)


async def seed_step_llm_configs_if_empty(session: AsyncSession) -> int:
    """Bootstrap one active pin per step from ``STEP_DEFAULTS`` when table is empty."""
    from sqlalchemy import func

    count = (
        await session.execute(select(func.count()).select_from(StepLLMConfig))
    ).scalar() or 0
    if count > 0:
        await load_active_step_pins(session)
        log.info("step_llm_config.already_seeded", count=count)
        return 0

    inserted = 0
    for step, (provider, model) in STEP_DEFAULTS.items():
        session.add(
            StepLLMConfig(
                id=uuid.uuid4(),
                step=step,
                provider=LLMProvider(provider),
                model_string=model,
                is_active=True,
                notes="Bootstrapped from STEP_DEFAULTS",
                created_by_admin_id=None,
            )
        )
        inserted += 1
    await session.flush()
    await load_active_step_pins(session)
    log.info("step_llm_config.seeded", inserted=inserted)
    return inserted


async def refresh_step_pin_cache(session: AsyncSession) -> int:
    """Reload cache after an admin write."""
    return await load_active_step_pins(session)


__all__ = [
    "load_active_step_pins",
    "refresh_step_pin_cache",
    "seed_step_llm_configs_if_empty",
]
