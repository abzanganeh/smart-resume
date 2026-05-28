from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class LLMMessage:
    role: str   # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


class LLMClient(ABC):
    """Unified interface every provider adapter must implement."""

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse: ...

    @abstractmethod
    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]: ...

    @property
    @abstractmethod
    def context_window(self) -> int:
        """Maximum tokens this model accepts."""
        ...

    @property
    @abstractmethod
    def supports_structured_output(self) -> bool:
        """True if the provider natively enforces a JSON schema."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...
