from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError

from app.llm.base import LLMClient, LLMMessage


class LLMParseError(Exception):
    pass


def _inject_schema_instruction(messages: list[LLMMessage], schema: type[BaseModel]) -> list[LLMMessage]:
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
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


def _append_parse_error(messages: list[LLMMessage], error: str) -> list[LLMMessage]:
    return list(messages) + [
        LLMMessage(
            role="user",
            content=f"Your previous response failed JSON validation with this error:\n{error}\n\nPlease fix it and output valid JSON only.",
        )
    ]


async def complete_structured(
    client: LLMClient,
    messages: list[LLMMessage],
    schema: type[BaseModel],
    max_retries: int = 3,
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> BaseModel:
    """
    Call the LLM and parse the result into a Pydantic model.
    Uses native JSON schema enforcement when the provider supports it,
    otherwise injects the schema into the prompt and retries on parse failure.
    """
    active_messages = list(messages)

    if not client.supports_structured_output:
        active_messages = _inject_schema_instruction(active_messages, schema)

    last_error: Exception | None = None

    for attempt in range(max_retries):
        if client.supports_structured_output:
            response = await client.complete(
                active_messages,
                response_schema=schema.model_json_schema(),
                max_tokens=max_tokens,
                temperature=temperature,
            )
        else:
            response = await client.complete(
                active_messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        try:
            # Strip markdown code fences if present
            content = response.content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
            return schema.model_validate_json(content)
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < max_retries - 1:
                active_messages = _append_parse_error(active_messages, str(e))

    raise LLMParseError(f"Failed to parse LLM output after {max_retries} attempts: {last_error}")
