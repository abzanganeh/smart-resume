"""Checkup rate limits and result cache (M18 slice 6)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.qa import QAOutput
from app.models.user import User
from app.services.auth.tokens import make_device_fingerprint
from app.services.billing.plan_code_resolver import resolve_plan_code_for_user
from app.services.billing.tier_limits_lookup import get_active_tier_limits
from app.services import session_store


_CHECKUP_CACHE_VERSION = "v2"


def checkup_result_cache_key(*, resume_text: str, jd_text: str) -> str:
    digest = hashlib.sha256(f"{resume_text}\0{jd_text}".encode()).hexdigest()
    return f"checkup:result:{_CHECKUP_CACHE_VERSION}:{digest}"


def checkup_device_counter_key(*, user_agent: str, client_ip: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    fp = make_device_fingerprint(user_agent, client_ip)
    return f"checkup:device:{fp}:{day}"


def checkup_user_period_key(*, user_id: str) -> str:
    month = datetime.now(timezone.utc).strftime("%Y%m")
    return f"checkup:user:{user_id}:{month}"


async def load_cached_checkup_result(cache_key: str) -> QAOutput | None:
    raw = await session_store.redis_get(cache_key)
    if not raw:
        return None
    return QAOutput.model_validate_json(raw)


async def store_cached_checkup_result(cache_key: str, result: QAOutput) -> None:
    await session_store.redis_set(
        cache_key,
        result.model_dump_json(),
        ex=24 * 3600,
    )


async def increment_checkup_device_count(*, user_agent: str, client_ip: str) -> int:
    key = checkup_device_counter_key(user_agent=user_agent, client_ip=client_ip)
    count = await session_store.redis_incr(key)
    if count == 1:
        await session_store.redis_expire(key, 24 * 3600)
    return count


async def enforce_anonymous_checkup_device_cap(*, user_agent: str, client_ip: str) -> None:
    count = await increment_checkup_device_count(
        user_agent=user_agent,
        client_ip=client_ip,
    )
    if count > settings.CHECKUP_DEVICE_DAILY_LIMIT:
        raise ValueError("checkup_device_daily_limit")


async def enforce_signed_in_checkup_quota(
    db: AsyncSession,
    *,
    user: User,
) -> None:
    plan_code = await resolve_plan_code_for_user(db, user)
    limits = await get_active_tier_limits(db, plan_code)
    if limits.checkups_per_period is None:
        return
    key = checkup_user_period_key(user_id=str(user.id))
    count = await session_store.redis_incr(key)
    if count == 1:
        await session_store.redis_expire(key, 32 * 24 * 3600)
    if count > limits.checkups_per_period:
        raise ValueError("checkup_period_limit")
