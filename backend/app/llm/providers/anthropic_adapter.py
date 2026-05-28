from __future__ import annotations

import json
from typing import AsyncIterator

import anthropic

from app.llm.base import LLMClient, LLMMessage, LLMResponse

_SCHEMA_TOOL_NAME = "structured_output"


class AnthropicAdapter(LLMClient):
    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    @property
    def context_window(self) -> int:
        return 200_000

    @property
    def supports_structured_output(self) -> bool:
        # Uses tool-use trick — handled in structured.py via prompt injection
        return False

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        system_parts = [m.content for m in messages if m.role == "system"]
        user_messages = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        system_text = "\n\n".join(system_parts)

        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_text,
            "messages": user_messages,
        }

        if response_schema:
            # Use tool-use to enforce structured JSON
            kwargs["tools"] = [
                {
                    "name": _SCHEMA_TOOL_NAME,
                    "description": "Output structured data conforming to the required schema.",
                    "input_schema": response_schema,
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": _SCHEMA_TOOL_NAME}

        resp = await self._client.messages.create(**kwargs)

        if response_schema:
            for block in resp.content:
                if block.type == "tool_use" and block.name == _SCHEMA_TOOL_NAME:
                    content = json.dumps(block.input)
                    break
            else:
                content = ""
        else:
            content = resp.content[0].text if resp.content else ""

        return LLMResponse(
            content=content,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=self._model,
            provider="anthropic",
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        system_parts = [m.content for m in messages if m.role == "system"]
        user_messages = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]

        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system="\n\n".join(system_parts),
            messages=user_messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
