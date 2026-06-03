from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from app.llm.base import LLMClient, LLMMessage


class LLMParseError(Exception):
    pass


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve all ``$ref`` pointers inline and drop the ``$defs`` block.

    Many providers reject schemas containing ``$defs`` / ``$ref``:
    - Gemini structured output rejects them outright ("Unknown field for
      Schema: $defs").
    - OpenAI strict mode requires fully self-contained schemas.
    - OpenRouter passes the schema text to models that don't understand
      JSON-Schema references (e.g. Llama 3.1 70B returns "Unknown field
      for Schema: $defs" when it sees them in the prompt).

    Returns a deep-copied schema with every ``$ref`` replaced by its target
    definition.  Idempotent on schemas that already lack ``$defs``.
    """
    if not isinstance(schema, dict):
        return schema

    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {}) or schema.pop("definitions", {}) or {}
    if not defs:
        return schema

    def _resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node and isinstance(node["$ref"], str):
                ref = node["$ref"]
                # Standard pointer: "#/$defs/Name" or "#/definitions/Name"
                if ref.startswith("#/$defs/"):
                    key = ref[len("#/$defs/"):]
                elif ref.startswith("#/definitions/"):
                    key = ref[len("#/definitions/"):]
                else:
                    return node
                target = defs.get(key)
                if target is None:
                    return node
                # Recursively resolve in case the target itself contains $refs
                resolved = _resolve(copy.deepcopy(target))
                # Merge in any sibling keys from the original node (e.g. "title")
                for k, v in node.items():
                    if k != "$ref":
                        resolved[k] = v
                return resolved
            return {k: _resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_resolve(item) for item in node]
        return node

    return _resolve(schema)


def _inject_schema_instruction(messages: list[LLMMessage], schema: type[BaseModel]) -> list[LLMMessage]:
    inlined = _inline_refs(schema.model_json_schema())
    schema_json = json.dumps(inlined, indent=2)
    instruction = (
        f"\n\nYou MUST respond with valid JSON that strictly conforms to this schema:\n"
        f"```json\n{schema_json}\n```\n"
        "Output ONLY the JSON object. No prose before or after it."
    )
    result = list(messages)
    # Append to last system message or add a new one
    for i in range(len(result) - 1, -1, -1):
        if result[i].role == "system":
            result[i] = LLMMessage(role="system", content=result[i].content + instruction)
            return result
    result.insert(0, LLMMessage(role="system", content=instruction))
    return result


def _is_truncated(error: str) -> bool:
    """Return True when the error indicates the LLM response was cut off mid-JSON."""
    lower = error.lower()
    return any(
        k in lower
        for k in (
            "eof while parsing",
            "unexpected end of input",
            "unexpected end of json",
            "unterminated string",
            "unexpected eof",
        )
    )


def _append_parse_error(messages: list[LLMMessage], error: str) -> list[LLMMessage]:
    if _is_truncated(error):
        instruction = (
            "Your previous response was cut off before the JSON was complete "
            "(the output hit the token limit mid-string). "
            "Please respond again with a shorter, more compact JSON. "
            "Rules for compactness:\n"
            "- Use brief descriptions (≤ 15 words each)\n"
            "- Keep blocking_issues to the 5 most important items\n"
            "- Keep quick_wins to at most 3 items\n"
            "- Keep checklist notes to ≤ 10 words each\n"
            "The JSON must be complete and valid — do not truncate it."
        )
    else:
        instruction = (
            f"Your previous response failed JSON validation with this error:\n{error}\n\n"
            "Please fix it and output valid JSON only."
        )
    return list(messages) + [LLMMessage(role="user", content=instruction)]


async def complete_structured(
    client: LLMClient,
    messages: list[LLMMessage],
    schema: type[BaseModel],
    max_retries: int = 3,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    accept_result: Callable[[BaseModel], str | None] | None = None,
) -> BaseModel:
    """
    Call the LLM and parse the result into a Pydantic model.
    Uses native JSON schema enforcement when the provider supports it,
    otherwise injects the schema into the prompt and retries on parse failure.
    """
    active_messages = list(messages)

    # Pre-compute the inlined schema once — providers that reject $defs
    # (Gemini, OpenAI strict mode) and prompt-injected models (OpenRouter
    # Llama, Ollama) all need a fully self-contained schema.
    inlined_schema = _inline_refs(schema.model_json_schema())

    if not client.supports_structured_output:
        active_messages = _inject_schema_instruction(active_messages, schema)

    last_error: Exception | None = None

    for attempt in range(max_retries):
        response = await client.complete(
            active_messages,
            response_schema=inlined_schema,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        try:
            # Strip markdown code fences if present
            content = response.content.strip()
            if not content:
                raise ValueError("LLM returned empty content")
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
            if content in ("{}", "[]", "null"):
                raise ValueError("LLM returned empty JSON object")
            parsed = schema.model_validate_json(content)
            if accept_result is not None:
                rejection = accept_result(parsed)
                if rejection:
                    raise ValueError(rejection)
            return parsed
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < max_retries - 1:
                active_messages = _append_parse_error(active_messages, str(e))

    raise LLMParseError(f"Failed to parse LLM output after {max_retries} attempts: {last_error}")
