"""Unit tests for notification_scheduler Lambda handler routing."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HANDLER_PATH = (
    Path(__file__).resolve().parents[3] / "infra" / "notification_scheduler" / "handler.py"
)


def _load_handler():
    spec = importlib.util.spec_from_file_location("notification_scheduler_handler", HANDLER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["notification_scheduler_handler"] = module
    spec.loader.exec_module(module)
    return module


def test_resolve_schedule_closure_tick_from_payload() -> None:
    handler = _load_handler()
    schedule = handler._resolve_schedule({"schedule": "closure_tick"})
    assert schedule == "closure_tick"


def test_supported_schedules_includes_closure_tick() -> None:
    handler = _load_handler()
    assert "closure_tick" in handler._SUPPORTED_SCHEDULES


def test_supported_schedules_includes_unverified_cleanup() -> None:
    handler = _load_handler()
    assert "unverified_cleanup" in handler._SUPPORTED_SCHEDULES


def test_resolve_schedule_unverified_cleanup_from_payload() -> None:
    handler = _load_handler()
    schedule = handler._resolve_schedule({"schedule": "unverified_cleanup"})
    assert schedule == "unverified_cleanup"
