"""In-process cache of active admin plan_code×step→model pins."""

from __future__ import annotations

from app.llm.model_registry import ModelRoute, PipelineStep

_pins: dict[tuple[str, PipelineStep], ModelRoute] = {}


def get_tier_step_pin(plan_code: str, step: PipelineStep) -> ModelRoute | None:
    return _pins.get((plan_code, step))


def set_tier_step_pins(pins: dict[tuple[str, PipelineStep], ModelRoute]) -> None:
    global _pins
    _pins = dict(pins)


def clear_tier_step_pins_for_tests() -> None:
    global _pins
    _pins = {}


__all__ = [
    "clear_tier_step_pins_for_tests",
    "get_tier_step_pin",
    "set_tier_step_pins",
]
