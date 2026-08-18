"""Unit tests for Career Watch SQS fan-out payloads (slice 5)."""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_HANDLER_PATH = (
    Path(__file__).resolve().parents[3] / "infra" / "career_page_poller" / "handler.py"
)


def _load_scheduler_handler():
    spec = importlib.util.spec_from_file_location(
        "career_page_poller_handler", _HANDLER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["career_page_poller_handler"] = module
    spec.loader.exec_module(module)
    return module


def test_build_enqueue_payload_roundtrip() -> None:
    handler = _load_scheduler_handler()
    company_id = str(uuid.uuid4())
    body = handler.build_enqueue_payload(company_id)
    parsed = json.loads(body)
    assert parsed["company_id"] == company_id


def test_build_enqueue_payload_rejects_invalid_uuid() -> None:
    handler = _load_scheduler_handler()
    with pytest.raises(ValueError):
        handler.build_enqueue_payload("not-a-uuid")
