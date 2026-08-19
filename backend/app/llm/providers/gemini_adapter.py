from __future__ import annotations

import copy
import json
from typing import Any, AsyncIterator

import google.generativeai as genai

from app.llm.base import LLMClient, LLMMessage, LLMResponse


# Gemini's responseSchema accepts only this subset of JSON Schema fields.
# Anything else (e.g. ``title``, ``default``, ``additionalProperties``,
# ``$defs``, ``anyOf``) makes the SDK raise ``ValueError: Unknown field
# for Schema: <name>`` before the request ever reaches the model.
_GEMINI_ALLOWED_KEYS = frozenset({
    "type", "format", "description", "nullable", "enum",
    "properties", "required", "items", "minItems", "maxItems",
    "propertyOrdering",
})


def _sanitize_schema_for_gemini(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip JSON-Schema fields Gemini's SDK rejects and convert ``anyOf``
    null-unions to ``nullable: true``.

    Idempotent. Recurses into ``properties``, ``items``, and ``anyOf``.
    """
    if not isinstance(schema, dict):
        return schema

    def _sanitize_schema_node(node: Any) -> Any:
        """Apply allowed-key filtering to a JSON-Schema node."""
        if not isinstance(node, dict):
            return node

        # Collapse Pydantic Optional[T] → {anyOf: [T, {type: null}]}
        # into a single Gemini-compatible nullable schema.
        any_of = node.get("anyOf")
        if isinstance(any_of, list):
            non_null = [opt for opt in any_of
                        if not (isinstance(opt, dict) and opt.get("type") == "null")]
            had_null = len(non_null) != len(any_of)
            if len(non_null) == 1 and isinstance(non_null[0], dict):
                merged = _sanitize_schema_node(copy.deepcopy(non_null[0]))
                # Carry over allowed sibling keys (e.g. "description").
                for k, v in node.items():
                    if k != "anyOf" and k in _GEMINI_ALLOWED_KEYS:
                        merged[k] = _sanitize_value(k, v)
                if had_null:
                    merged["nullable"] = True
                return merged
            # Unhandled anyOf shape — drop it and keep allowed siblings.

        result: dict[str, Any] = {}
        for k, v in node.items():
            if k == "anyOf":
                continue
            if k not in _GEMINI_ALLOWED_KEYS:
                continue
            result[k] = _sanitize_value(k, v)
        return result

    def _sanitize_value(parent_key: str, value: Any) -> Any:
        """Recurse with context — ``properties`` values are schemas keyed by
        user-defined property names, ``items`` is a single schema, ``required``
        and ``enum`` are lists of literal values that must pass through."""
        if parent_key == "properties" and isinstance(value, dict):
            return {prop_name: _sanitize_schema_node(prop_schema)
                    for prop_name, prop_schema in value.items()}
        if parent_key == "items":
            if isinstance(value, list):
                return [_sanitize_schema_node(v) for v in value]
            return _sanitize_schema_node(value)
        if parent_key in {"required", "enum"}:
            return value
        if isinstance(value, dict):
            return _sanitize_schema_node(value)
        if isinstance(value, list):
            return [_sanitize_schema_node(v) if isinstance(v, dict) else v
                    for v in value]
        return value

    return _sanitize_schema_node(copy.deepcopy(schema))


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

    def _needs_thinking_headroom(self) -> bool:
        """Gemini 3.x spends hidden tokens on reasoning before visible text."""
        name = self._model_name.lower()
        return "gemini-3" in name or name.startswith("gemini-3")

    def _output_token_cap(self, max_tokens: int) -> int:
        if self._needs_thinking_headroom():
            return max(max_tokens, 4096)
        return max_tokens

    def _visible_text(self, resp: Any) -> str:
        try:
            text = resp.text or ""
            if text:
                return text
        except ValueError:
            text = ""
        parts_text: list[str] = []
        for cand in getattr(resp, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", None) or []:
                if getattr(part, "thought", False):
                    continue
                piece = getattr(part, "text", None)
                if piece:
                    parts_text.append(piece)
        return "".join(parts_text)

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
            max_output_tokens=self._output_token_cap(max_tokens),
        )
        if response_schema:
            sanitized_schema = _sanitize_schema_for_gemini(response_schema)
            generation_config = genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=self._output_token_cap(max_tokens),
                response_mime_type="application/json",
                response_schema=sanitized_schema,
            )

        model = genai.GenerativeModel(
            self._model_name,
            system_instruction=system_text if system_text else None,
        )
        resp = await model.generate_content_async(
            contents,
            generation_config=generation_config,
        )
        content = self._visible_text(resp)
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
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=self._output_token_cap(max_tokens),
            ),
            stream=True,
        )
        async for chunk in resp:
            if chunk.text:
                yield chunk.text
