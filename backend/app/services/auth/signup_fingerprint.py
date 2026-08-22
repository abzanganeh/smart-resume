"""Signup device fingerprint hashing (stored hashed only)."""

from __future__ import annotations

import hashlib

from fastapi import Request

from app.services.admin_auth.tokens import make_ua_fingerprint


def hash_signup_device_fingerprint(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


def derive_signup_device_fingerprint_hash(
    request: Request,
    *,
    client_fingerprint: str | None = None,
) -> str | None:
    """Build a hashed signup fingerprint from client input or request headers."""
    if client_fingerprint and len(client_fingerprint.strip()) >= 16:
        return hash_signup_device_fingerprint(client_fingerprint)

    user_agent = request.headers.get("user-agent", "").strip()
    if not user_agent:
        return None

    return make_ua_fingerprint(
        user_agent,
        request.headers.get("accept-language", ""),
    )


__all__ = ["derive_signup_device_fingerprint_hash", "hash_signup_device_fingerprint"]
