from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from app.llm.base import LLMClient, LLMMessage, LLMResponse


class OllamaAdapter(LLMClient):
    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    @property
    def context_window(self) -> int:
        return 128_000

    @property
    def supports_structured_output(self) -> bool:
        return False

    @property
    def provider_name(self) -> str:
        return "ollama"

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
        payload: dict = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if response_schema:
            payload["format"] = response_schema

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data.get("message", {}).get("content", "")
        return LLMResponse(
            content=content,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            model=self._model,
            provider="ollama",
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", f"{self._base_url}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                yield token
                        except json.JSONDecodeError:
                            continue
