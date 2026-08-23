from __future__ import annotations

from collections.abc import AsyncIterator

from app.llm.base import LLMClient, LLMMessage, LLMResponse
from app.llm.token_accounting import record_llm_response


class TrackingLLMClient(LLMClient):
    """Wrap a provider adapter and record real token usage on every completion."""

    def __init__(self, inner: LLMClient) -> None:
        self._inner = inner

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        response = await self._inner.complete(
            messages,
            response_schema=response_schema,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        await record_llm_response(response)
        return response

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        async for chunk in self._inner.stream(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
        ):
            yield chunk

    @property
    def context_window(self) -> int:
        return self._inner.context_window

    @property
    def supports_structured_output(self) -> bool:
        return self._inner.supports_structured_output

    @property
    def provider_name(self) -> str:
        return self._inner.provider_name

    @property
    def model_name(self) -> str:
        return self._inner.model_name
