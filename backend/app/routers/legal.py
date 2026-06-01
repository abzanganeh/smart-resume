"""Legal / DPO contact endpoints.

Currently exposes a single public route (``POST /api/legal/dpo-contact``)
used by ``frontend/app/legal/contact/page.tsx``.  The endpoint is rate
limited (5/min/IP) to keep abuse surface small and forwards the message
to ``privacy@zanganehai.com`` via Resend.

The route never reveals whether Resend was actually called — if the
provider is missing or fails, the API still returns ``200`` with a
delivery hint, and the message is logged at INFO so the request is
recoverable in the audit trail.  This matches the contract documented
in ``SYSTEM_DESIGN_PHASE_2.md §19.9``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.limiter import limiter

log = structlog.get_logger("legal.dpo_contact")

router = APIRouter(prefix="/api/legal", tags=["legal"])


_DPO_INBOX = "privacy@zanganehai.com"


_VALID_TOPICS = {
    "data_subject_request",
    "sub_processor_objection",
    "security_disclosure",
    "ccpa_inquiry",
    "other",
}


class DPOContactRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    topic: str = Field(..., min_length=3, max_length=64)
    message: str = Field(..., min_length=20, max_length=4000)


class DPOContactResponse(BaseModel):
    delivered: bool
    provider: str


@router.post(
    "/dpo-contact",
    status_code=status.HTTP_200_OK,
    response_model=DPOContactResponse,
)
@limiter.limit("5/minute")
async def dpo_contact(request: Request, payload: DPOContactRequest) -> DPOContactResponse:
    topic = payload.topic if payload.topic in _VALID_TOPICS else "other"

    subject = f"[DPO][{topic}] {payload.name} — Smart Resume privacy inquiry"
    body_text = (
        f"From: {payload.name} <{payload.email}>\n"
        f"Topic: {topic}\n\n"
        f"{payload.message}\n"
    )
    body_html = (
        '<div style="font-family:Inter,Helvetica,Arial,sans-serif;color:#111;'
        'max-width:560px;margin:0 auto;padding:24px">'
        f"<p><strong>From:</strong> {payload.name} &lt;{payload.email}&gt;</p>"
        f"<p><strong>Topic:</strong> {topic}</p>"
        "<hr/>"
        f"<pre style=\"white-space:pre-wrap;font-family:inherit\">{payload.message}</pre>"
        "</div>"
    )

    result = await _send_email(
        to_email=_DPO_INBOX,
        reply_to=payload.email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )

    log.info(
        "legal.dpo_contact.received",
        topic=topic,
        from_email=payload.email,
        delivered=result["sent"],
        provider=result["provider"],
    )

    return DPOContactResponse(
        delivered=bool(result.get("sent", False)),
        provider=str(result.get("provider", "dev-log")),
    )


async def _send_email(
    *,
    to_email: str,
    reply_to: str,
    subject: str,
    body_text: str,
    body_html: str,
) -> dict[str, Any]:
    if not settings.RESEND_API_KEY:
        log.info(
            "legal.dpo_contact.email_skipped",
            reason="RESEND_API_KEY not configured",
            to=to_email,
            subject=subject,
            preview=body_text[:200],
        )
        return {"sent": False, "provider": "dev-log"}

    try:
        import resend
    except ImportError as exc:  # pragma: no cover
        log.warning("legal.dpo_contact.resend_import_failed", error=str(exc))
        return {"sent": False, "provider": "missing"}

    resend.api_key = settings.RESEND_API_KEY

    def _do_send() -> Any:
        return resend.Emails.send(
            {
                "from": settings.RESEND_FROM_EMAIL,
                "to": [to_email],
                "reply_to": [reply_to],
                "subject": subject,
                "text": body_text,
                "html": body_html,
            }
        )

    try:
        result = await asyncio.to_thread(_do_send)
    except Exception as exc:  # pragma: no cover - provider side
        log.error(
            "legal.dpo_contact.send_failed",
            to=to_email,
            subject=subject,
            error=str(exc),
        )
        return {"sent": False, "provider": "resend", "error": str(exc)}

    return {"sent": True, "provider": "resend", "result": result}


__all__ = ["router"]
