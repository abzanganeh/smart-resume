from __future__ import annotations

from collections.abc import AsyncIterator

from app.llm.base import LLMClient, LLMMessage, LLMResponse
from app.llm.token_accounting import _llm_user_id, record_llm_response
from app.services.billing.free_tier_budget import assert_free_user_llm_allowed


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
        await assert_free_user_llm_allowed(_llm_user_id.get())
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
        await assert_free_user_llm_allowed(_llm_user_id.get())
        parts: list[str] = []
        async for chunk in self._inner.stream(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
        ):
            parts.append(chunk)
            yield chunk

        input_tokens = int(getattr(self._inner, "last_stream_input_tokens", 0) or 0)
        output_tokens = int(getattr(self._inner, "last_stream_output_tokens", 0) or 0)
        text = "".join(parts)
        if output_tokens <= 0 and text:
            output_tokens = max(1, len(text) // 4)

        if text or input_tokens > 0 or output_tokens > 0:
            await record_llm_response(
                LLMResponse(
                    content=text,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=self._inner.model_name,
                    provider=self._inner.provider_name,
                )
            )

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
