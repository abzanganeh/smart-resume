"""Resend-backed transactional email for verification + password reset.

The Resend SDK is synchronous, so all calls are dispatched via
``asyncio.to_thread`` to avoid blocking the event loop.  Missing API
keys do not raise in dev — the email body is logged at ``INFO`` so
local engineers can copy the link out of the terminal.

Both flows mint single-purpose JWTs:

- ``verify``: 24 h TTL, idempotent — re-sending is allowed.
- ``reset``: 1 h TTL — used by ``POST /api/auth/password/reset`` which
  invalidates all of the user's refresh tokens on success.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog

from app.config import settings
from app.services.auth.tokens import create_purpose_token

log = structlog.get_logger("auth.email")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def make_email_verification_token(user_id: uuid.UUID) -> str:
    return create_purpose_token(
        user_id, typ="verify", ttl=settings.EMAIL_VERIFY_TTL_SECONDS
    )


def make_password_reset_token(user_id: uuid.UUID) -> str:
    return create_purpose_token(
        user_id, typ="reset", ttl=settings.PASSWORD_RESET_TTL_SECONDS
    )


def verification_link(token: str) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/auth/verify?token={token}"


def password_reset_link(token: str) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/auth/reset?token={token}"


async def send_verification_email(
    *,
    to_email: str,
    user_id: uuid.UUID,
    display_name: str | None = None,
) -> dict[str, Any]:
    token = make_email_verification_token(user_id)
    link = verification_link(token)
    name = display_name or to_email.split("@", 1)[0]
    subject = "Verify your TalioCV email"
    body_text = (
        f"Hi {name},\n\n"
        "Please confirm your TalioCV email by clicking the link below "
        "within the next 24 hours:\n\n"
        f"{link}\n\n"
        "If you did not create an account, you can safely ignore this message."
    )
    body_html = _wrap_html(
        f"<p>Hi {name},</p>"
        "<p>Please confirm your TalioCV email by clicking the button below "
        "within the next 24 hours.</p>"
        f'<p><a href="{link}" '
        'style="display:inline-block;padding:10px 18px;background:#0d9488;'
        'color:#fff;text-decoration:none;border-radius:6px">Verify email</a></p>'
        f'<p style="font-size:12px;color:#666">Or paste this link into your browser:<br/>{link}</p>'
    )
    return await _send(to_email, subject, body_text, body_html, token=token)


async def send_password_reset_email(
    *,
    to_email: str,
    user_id: uuid.UUID,
    display_name: str | None = None,
) -> dict[str, Any]:
    token = make_password_reset_token(user_id)
    link = password_reset_link(token)
    name = display_name or to_email.split("@", 1)[0]
    subject = "Reset your TalioCV password"
    body_text = (
        f"Hi {name},\n\n"
        "We received a request to reset your TalioCV password. "
        "Use the link below within the next hour to choose a new one:\n\n"
        f"{link}\n\n"
        "If you did not request this, you can safely ignore this email — "
        "your current password remains in effect."
    )
    body_html = _wrap_html(
        f"<p>Hi {name},</p>"
        "<p>We received a request to reset your TalioCV password. "
        "Use the button below within the next hour to choose a new one.</p>"
        f'<p><a href="{link}" '
        'style="display:inline-block;padding:10px 18px;background:#dc2626;'
        'color:#fff;text-decoration:none;border-radius:6px">Reset password</a></p>'
        f'<p style="font-size:12px;color:#666">Or paste this link into your browser:<br/>{link}</p>'
    )
    return await _send(to_email, subject, body_text, body_html, token=token)


async def send_account_deleted_email(
    *,
    to_email: str,
    display_name: str | None = None,
) -> dict[str, Any]:
    name = display_name or to_email.split("@", 1)[0]
    subject = "Your TalioCV account has been deleted"
    body_text = (
        f"Hi {name},\n\n"
        "Your TalioCV account and associated data have been permanently deleted "
        "as requested.\n\n"
        "If you believe this was a mistake, please contact support."
    )
    body_html = _wrap_html(
        f"<p>Hi {name},</p>"
        "<p>Your TalioCV account and associated data have been permanently "
        "deleted as requested.</p>"
        "<p>If you believe this was a mistake, please contact support.</p>"
    )
    return await _send(to_email, subject, body_text, body_html, token="")


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _wrap_html(inner: str) -> str:
    return (
        '<div style="font-family:Inter,Helvetica,Arial,sans-serif;color:#111;'
        'max-width:560px;margin:0 auto;padding:24px">'
        f"{inner}"
        '<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0"/>'
        '<p style="font-size:11px;color:#9ca3af">TalioCV — '
        "automated message, please do not reply.</p>"
        "</div>"
    )


async def _send(
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str,
    *,
    token: str,
) -> dict[str, Any]:
    if not settings.RESEND_API_KEY:
        log.info(
            "auth.email.skipped",
            reason="RESEND_API_KEY not configured",
            to=to_email,
            subject=subject,
            preview=body_text[:200],
        )
        return {"sent": False, "provider": "dev-log", "token": token}

    try:
        import resend  # local import keeps unit tests light
    except ImportError as exc:  # pragma: no cover
        log.warning("auth.email.resend_import_failed", error=str(exc))
        return {"sent": False, "provider": "missing", "token": token}

    resend.api_key = settings.RESEND_API_KEY

    def _do_send() -> Any:
        return resend.Emails.send(
            {
                "from": settings.RESEND_FROM_EMAIL,
                "to": [to_email],
                "subject": subject,
                "text": body_text,
                "html": body_html,
            }
        )

    try:
        result = await asyncio.to_thread(_do_send)
    except Exception as exc:  # pragma: no cover - provider side
        log.error(
            "auth.email.send_failed",
            to=to_email,
            subject=subject,
            error=str(exc),
        )
        return {"sent": False, "provider": "resend", "error": str(exc), "token": token}

    log.info("auth.email.sent", to=to_email, subject=subject, provider="resend")
    return {"sent": True, "provider": "resend", "result": result, "token": token}


__all__ = [
    "make_email_verification_token",
    "make_password_reset_token",
    "password_reset_link",
    "send_account_deleted_email",
    "send_password_reset_email",
    "send_verification_email",
    "verification_link",
]
