"""Cloudflare Turnstile server-side verification."""

from __future__ import annotations

import httpx
import structlog

from app.config import settings

log = structlog.get_logger("auth.turnstile")

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

DUMMY_TURNSTILE_SITE_KEYS = frozenset(
    {
        "1x00000000000000000000AA",
        "2x00000000000000000000AB",
    }
)
DUMMY_TURNSTILE_SECRET_KEYS = frozenset(
    {
        "1x0000000000000000000000000000000AA",
        "2x0000000000000000000000000000000AA",
    }
)


def assert_turnstile_production_keys() -> None:
    """Refuse production boot when Turnstile still uses Cloudflare dummy keys."""
    if settings.APP_ENV != "production":
        return
    site = settings.TURNSTILE_SITE_KEY.strip()
    secret = settings.TURNSTILE_SECRET_KEY.strip()
    if not site or not secret:
        raise RuntimeError("production requires TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY")
    if site in DUMMY_TURNSTILE_SITE_KEYS or secret in DUMMY_TURNSTILE_SECRET_KEYS:
        raise RuntimeError("production refuses Cloudflare Turnstile dummy keys")


async def verify_turnstile_token(*, token: str, remote_ip: str | None = None) -> bool:
    """Verify a Turnstile response token with Cloudflare."""
    secret = settings.TURNSTILE_SECRET_KEY.strip()
    if not secret or not token.strip():
        return False

    payload: dict[str, str] = {"secret": secret, "response": token.strip()}
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(TURNSTILE_VERIFY_URL, data=payload)
            resp.raise_for_status()
            body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("auth.turnstile.verify_failed", error=str(exc))
        return False

    success = bool(body.get("success"))
    if not success:
        log.info(
            "auth.turnstile.rejected",
            error_codes=body.get("error-codes"),
        )
    return success


__all__ = [
    "assert_turnstile_production_keys",
    "verify_turnstile_token",
]
