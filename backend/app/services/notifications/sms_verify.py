"""SMS phone verification via Redis + Twilio."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import string

import structlog

from app.config import settings
from app.services import session_store

log = structlog.get_logger("notifications.sms_verify")

_KEY_FMT = "sms_verify:{user_id}"
_TTL_SECONDS = 600
_memory: dict[str, str] = {}


def _code() -> str:
    alphabet = string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


def _hash_code(*, code: str, salt: str, user_id: str) -> str:
    secret = settings.AUTH_SECRET or settings.BYOK_ENCRYPTION_KEY or "dev-sms-secret"
    digest = hashlib.sha256(f"{secret}:{user_id}:{salt}:{code}".encode("utf-8")).hexdigest()
    return digest


async def store_pending_code(user_id: str, phone: str) -> str:
    code = _code()
    salt = secrets.token_hex(8)
    code_hash = _hash_code(code=code, salt=salt, user_id=user_id)
    payload = json.dumps({"phone": phone, "salt": salt, "code_hash": code_hash})
    key = _KEY_FMT.format(user_id=user_id)
    r = session_store._redis_client  # type: ignore[attr-defined]
    if r is not None:
        await r.hset(
            key,
            mapping={
                "phone": phone,
                "salt": salt,
                "code_hash": code_hash,
            },
        )
        await r.expire(key, _TTL_SECONDS)
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
    submitted = code.strip()
    if r is not None:
        salt = await r.hget(key, "salt")
        if not salt:
            return False, None
        candidate = _hash_code(code=submitted, salt=salt, user_id=user_id)
        script = """
local key = KEYS[1]
local expected = ARGV[1]
local stored = redis.call('HGET', key, 'code_hash')
if not stored then
  return {'0', ''}
end
local phone = redis.call('HGET', key, 'phone') or ''
if stored == expected then
  redis.call('DEL', key)
  return {'1', phone}
end
return {'0', phone}
"""
        raw = await r.eval(script, 1, key, candidate)
        ok = str(raw[0]) == "1"
        phone = str(raw[1]) if len(raw) > 1 and raw[1] else None
        return ok, phone

    raw = _memory.get(key)
    if not raw:
        return False, None
    data = json.loads(raw)
    candidate = _hash_code(
        code=submitted,
        salt=data.get("salt", ""),
        user_id=user_id,
    )
    if not hmac.compare_digest(candidate, data.get("code_hash", "")):
        return False, data.get("phone")
    _memory.pop(key, None)
    return True, data.get("phone")


__all__ = ["send_verification_sms", "store_pending_code", "verify_code"]
