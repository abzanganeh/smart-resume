from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.llm.base import LLMMessage
from app.llm.factory import get_llm_client

router = APIRouter(prefix="/api/llm", tags=["llm"])


class VerifyRequest(BaseModel):
    provider: str
    model: str


def _friendly_error(exc: Exception) -> str:
    msg = str(exc).lower()
    name = type(exc).__name__

    if "authentication" in name.lower() or "invalid_api_key" in msg or "401" in msg:
        return "Invalid API key. Check that you copied the full key with no extra spaces."
    if "403" in msg or "permission" in msg:
        return "Key rejected — check billing or API access on the provider dashboard."
    if "404" in msg and "model" in msg:
        return (
            "Key works, but this model id is not available (it may be retired). "
            "Try gemini-3.6-flash or gemini-3.5-flash-lite."
        )
    if "rate" in msg and "limit" in msg:
        return "Key is valid but rate-limited. Wait a moment and try again."
    if "connection refused" in msg or "connect" in msg:
        return "Could not reach the provider. For Ollama, make sure it is running locally."
    return f"Verification failed: {exc}"


@router.post("/verify")
async def verify_llm_key(body: VerifyRequest):
    """
    Make a tiny LLM call to verify provider + model using platform keys.
    Always returns 200 with { valid: bool, message: str } — never throws for bad keys.
    """
    try:
        llm = get_llm_client(body.provider, body.model)
        await llm.complete(
            [LLMMessage(role="user", content='Reply with exactly: OK')],
            max_tokens=5,
            temperature=0,
        )
        return {
            "valid": True,
            "message": "Connection successful — platform key and model work.",
            "provider": body.provider,
            "model": body.model,
        }
    except Exception as exc:
        return {
            "valid": False,
            "message": _friendly_error(exc),
            "provider": body.provider,
            "model": body.model,
        }
