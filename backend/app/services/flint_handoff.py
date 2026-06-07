"""Ephemeral cross-product handoff tokens for Flint import (Strategy B Phase 1).

Tokens are single-use, short-lived, and stored separately from tailoring
sessions so redeem does not require Smart Resume JWT auth.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import HTTPException, status

from app.config import settings
from app.models.session import Session
from app.services.export_service import render_txt
from app.services.session_store import (
    get_session,
    redis_getdel,
    redis_incr,
    redis_set_nx,
)

log = structlog.get_logger()

_HANDOFF_PREFIX = "flint:handoff:"
_RATE_PREFIX = "flint:handoff:rate:"
_RESUME_SUMMARY_MAX = 2000
_EXPORT_VERSION = 1


def _handoff_key(token: str) -> str:
    return f"{_HANDOFF_PREFIX}{token}"


def _rate_key(client_ip: str) -> str:
    return f"{_RATE_PREFIX}{client_ip}"


def _derive_session_name(session: Session) -> str:
    company = ""
    role = "Interview"

    if session.phase2_output is not None:
        audit = session.phase2_output
        if getattr(audit, "company", None):
            company = str(audit.company).strip()

    if not company and session.phase3_output is not None:
        contact = session.phase3_output.contact or {}
        if isinstance(contact, dict):
            company = str(contact.get("company") or "").strip()

    if not company and session.jd_raw:
        first_line = session.jd_raw.strip().splitlines()[0][:120]
        company = first_line.strip()

    if session.phase3_output is not None:
        contact = session.phase3_output.contact or {}
        if isinstance(contact, dict):
            title = str(contact.get("title") or contact.get("name") or "").strip()
            if title:
                role = title

    if company:
        return f"{company} — {role}"
    return role


def _derive_domain(session: Session) -> str:
    if session.phase1_output is not None:
        primary = session.phase1_output.role_context.primary_domain.strip()
        if primary:
            return primary
    return "software engineering"


def build_handoff_payload(session: Session) -> dict[str, Any]:
    """Build the JSON blob stored in Redis for a handoff token."""
    if session.phase3_output is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No tailored resume yet. Complete Phase 3 before opening in Flint.",
        )
    if not session.jd_raw or not session.jd_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No job description on this session.",
        )

    resume_summary = render_txt(session)[:_RESUME_SUMMARY_MAX]

    return {
        "session_name": _derive_session_name(session),
        "session_type": "interview",
        "domain": _derive_domain(session),
        "jd_text": session.jd_raw.strip(),
        "resume_summary": resume_summary,
        "smart_resume_session_id": session.session_id,
        "export_version": _EXPORT_VERSION,
        "user_id": session.user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def create_handoff_token(session: Session) -> tuple[str, int]:
    """Mint a single-use token. Returns (token, expires_in_seconds)."""
    payload = build_handoff_payload(session)
    token = str(uuid.uuid4())
    ttl = settings.FLINT_HANDOFF_TTL_SECONDS
    key = _handoff_key(token)
    stored = await redis_set_nx(key, json.dumps(payload), ex=ttl)
    if not stored:
        # UUID collision — astronomically unlikely; retry once.
        token = str(uuid.uuid4())
        key = _handoff_key(token)
        stored = await redis_set_nx(key, json.dumps(payload), ex=ttl)
        if not stored:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not create handoff token. Please try again.",
            )
    return token, ttl


async def redeem_handoff_token(token: str, *, client_ip: str) -> dict[str, Any]:
    """Atomically fetch and delete a handoff payload. Public endpoint."""
    if not token or len(token) > 64:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired link")

    count = await redis_incr(_rate_key(client_ip))
    if count == 1:
        from app.services.session_store import redis_expire

        await redis_expire(_rate_key(client_ip), 60)
    if count > 10:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again shortly.",
        )

    raw = await redis_getdel(_handoff_key(token))
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link expired or already used",
        )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("flint_handoff.corrupt_payload")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired link",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired link")

    return payload


async def assert_session_owned(session_id: str, user_id: str) -> Session:
    """Load a tailoring session and verify it belongs to the authenticated user."""
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if not session.user_id or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session access denied")
    return session
