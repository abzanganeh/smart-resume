from __future__ import annotations

import json
from typing import AsyncIterator

import google.generativeai as genai

from app.llm.base import LLMClient, LLMMessage, LLMResponse


class GeminiAdapter(LLMClient):
    def __init__(self, model: str, api_key: str) -> None:
        self._model_name = model
        genai.configure(api_key=api_key)
        self._client = genai.GenerativeModel(model)

    @property
    def context_window(self) -> int:
        return 1_000_000  # Gemini 1.5 Pro

    @property
    def supports_structured_output(self) -> bool:
        return True

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _build_contents(self, messages: list[LLMMessage]) -> tuple[str, list[dict]]:
        system_text = "\n\n".join(m.content for m in messages if m.role == "system")
        contents = [{"role": m.role if m.role != "assistant" else "model", "parts": [m.content]}
                    for m in messages if m.role != "system"]
        return system_text, contents

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        system_text, contents = self._build_contents(messages)
        generation_config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if response_schema:
            generation_config = genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
                response_schema=response_schema,
            )

        model = genai.GenerativeModel(
            self._model_name,
            system_instruction=system_text if system_text else None,
        )
        resp = await model.generate_content_async(
            contents,
            generation_config=generation_config,
        )
        content = resp.text or ""
        usage = resp.usage_metadata
        return LLMResponse(
            content=content,
            input_tokens=usage.prompt_token_count if usage else 0,
            output_tokens=usage.candidates_token_count if usage else 0,
            model=self._model_name,
            provider="gemini",
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        system_text, contents = self._build_contents(messages)
        model = genai.GenerativeModel(
            self._model_name,
            system_instruction=system_text if system_text else None,
        )
        resp = await model.generate_content_async(
            contents,
            generation_config=genai.GenerationConfig(temperature=temperature, max_output_tokens=max_tokens),
            stream=True,
        )
        async for chunk in resp:
            if chunk.text:
                yield chunk.text
