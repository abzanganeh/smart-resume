"""OpenAI adapter token parameter selection for GPT-5 models."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.base import LLMMessage
from app.llm.providers.openai_adapter import OpenAIAdapter


_FAKE_KEY = "unit-test-placeholder-not-a-secret"


@pytest.mark.asyncio
async def test_gpt5_uses_max_completion_tokens() -> None:
    adapter = OpenAIAdapter(model="gpt-5-mini", api_key=_FAKE_KEY)
    mock_create = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"ok": true}'))],
            usage=MagicMock(prompt_tokens=10, completion_tokens=5),
        )
    )
    adapter._client.chat.completions.create = mock_create

    await adapter.complete([LLMMessage(role="user", content="hi")])

    kwargs = mock_create.await_args.kwargs
    assert "max_completion_tokens" in kwargs
    assert "max_tokens" not in kwargs


@pytest.mark.asyncio
async def test_gpt4o_uses_max_tokens() -> None:
    adapter = OpenAIAdapter(model="gpt-4o-mini", api_key=_FAKE_KEY)
    mock_create = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"ok": true}'))],
            usage=MagicMock(prompt_tokens=10, completion_tokens=5),
        )
    )
    adapter._client.chat.completions.create = mock_create

    await adapter.complete([LLMMessage(role="user", content="hi")])

    kwargs = mock_create.await_args.kwargs
    assert "max_tokens" in kwargs
    assert "max_completion_tokens" not in kwargs
