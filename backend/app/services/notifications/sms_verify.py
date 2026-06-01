"""SMS phone verification via Redis + Twilio."""

from __future__ import annotations

import asyncio
import json
import random
import string

import structlog

from app.config import settings
from app.services import session_store

log = structlog.get_logger("notifications.sms_verify")

_KEY_FMT = "sms_verify:{user_id}"
_TTL_SECONDS = 600
_memory: dict[str, str] = {}


def _code() -> str:
    return "".join(random.choices(string.digits, k=6))


async def store_pending_code(user_id: str, phone: str) -> str:
    code = _code()
    payload = json.dumps({"phone": phone, "code": code})
    key = _KEY_FMT.format(user_id=user_id)
    r = session_store._redis_client  # type: ignore[attr-defined]
    if r is not None:
        await r.setex(key, _TTL_SECONDS, payload)
    else:
        _memory[key] = payload
    return code


async def send_verification_sms(phone: str, code: str) -> dict:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        log.info("notifications.sms_verify.dev", phone=phone, code=code)
        return {"sent": True, "provider": "dev-log", "code": code}
    try:
        from twilio.rest import Client
    except ImportError:
        return {"sent": False, "provider": "missing"}

    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    def _send():
        return client.messages.create(
            body=f"Your Smart Resume verification code is {code}",
            from_=settings.TWILIO_FROM_NUMBER,
            to=phone,
        )

    message = await asyncio.to_thread(_send)
    return {"sent": True, "provider": "twilio", "sid": message.sid}


async def verify_code(user_id: str, code: str) -> tuple[bool, str | None]:
    key = _KEY_FMT.format(user_id=user_id)
    r = session_store._redis_client  # type: ignore[attr-defined]
    raw: str | None = None
    if r is not None:
        raw = await r.get(key)
        if raw:
            await r.delete(key)
    else:
        raw = _memory.pop(key, None)
    if not raw:
        return False, None
    data = json.loads(raw)
    if data.get("code") != code.strip():
        return False, data.get("phone")
    return True, data.get("phone")


__all__ = ["send_verification_sms", "store_pending_code", "verify_code"]
