"""In-process cache of active admin step→model pins.

``resolve_model`` reads this cache synchronously; startup and admin writes
refresh it from ``step_llm_configs``.
"""

from __future__ import annotations

from app.llm.model_registry import ModelRoute, PipelineStep

_pins: dict[PipelineStep, ModelRoute] = {}


def get_step_pin(step: PipelineStep) -> ModelRoute | None:
    return _pins.get(step)


def set_step_pins(pins: dict[PipelineStep, ModelRoute]) -> None:
    global _pins
    _pins = dict(pins)


def clear_step_pins_for_tests() -> None:
    global _pins
    _pins = {}


__all__ = [
    "clear_step_pins_for_tests",
    "get_step_pin",
    "set_step_pins",
]
