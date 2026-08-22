"""Unit tests for the apify_cache_worker spend kill switch."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HANDLER_PATH = (
    Path(__file__).resolve().parents[3] / "infra" / "apify_cache_worker" / "handler.py"
)


def _load_handler():
    spec = importlib.util.spec_from_file_location("apify_cache_worker_handler", HANDLER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["apify_cache_worker_handler"] = module
    spec.loader.exec_module(module)
    return module


def _fail(*args, **kwargs):  # pragma: no cover - only runs on regression
    raise AssertionError("disabled worker must not query Postgres or start actor runs")


def test_handler_skips_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Absent config must mean no spend, not a crash on the missing token."""
    handler = _load_handler()
    monkeypatch.delenv("APIFY_CACHE_ENABLED", raising=False)
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.setattr(handler, "_fetch_top_queries", _fail)
    monkeypatch.setattr(handler, "_run_apify_scraper", _fail)

    assert handler.handler({}, None) == {"skipped": True, "reason": "disabled"}


def test_handler_skips_when_explicitly_false(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _load_handler()
    monkeypatch.setenv("APIFY_CACHE_ENABLED", "false")
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_api_token")
    monkeypatch.setattr(handler, "_fetch_top_queries", _fail)
    monkeypatch.setattr(handler, "_run_apify_scraper", _fail)

    assert handler.handler({}, None) == {"skipped": True, "reason": "disabled"}


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", " true "])
def test_is_enabled_accepts_truthy_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    handler = _load_handler()
    monkeypatch.setenv("APIFY_CACHE_ENABLED", value)
    assert handler._is_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "", "off"])
def test_is_enabled_rejects_other_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    handler = _load_handler()
    monkeypatch.setenv("APIFY_CACHE_ENABLED", value)
    assert handler._is_enabled() is False
