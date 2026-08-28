"""Unit tests for DeepSeek factory wiring."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.llm.factory import get_llm_client
from app.llm.providers.deepseek_adapter import DeepSeekAdapter
from app.llm.tracking_client import TrackingLLMClient


_FAKE_KEY = "unit-test-placeholder-not-a-secret"


def test_get_llm_client_returns_deepseek_adapter_wrapped_in_tracking() -> None:
    with patch("app.llm.factory.settings") as mock_settings:
        mock_settings.DEEPSEEK_API_KEY = "x" * 32
        client = get_llm_client(provider="deepseek", model="deepseek-v4-flash")

    assert isinstance(client, TrackingLLMClient)
    assert isinstance(client._inner, DeepSeekAdapter)
    assert client.provider_name == "deepseek"
    assert client.model_name == "deepseek-v4-flash"


def test_deepseek_adapter_provider_metadata() -> None:
    adapter = DeepSeekAdapter(model="deepseek-v4-flash", api_key=_FAKE_KEY)
    assert adapter.provider_name == "deepseek"
    assert adapter.model_name == "deepseek-v4-flash"
    assert adapter.supports_structured_output is True
