"""Flint cross-product handoff routes (Strategy B Phase 1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.limiter import limiter
from app.models.user import User
from app.services.auth.client_ip import resolve_client_ip
from app.services.auth.dependencies import get_current_user
from app.services.flint_handoff import (
    assert_session_owned,
    create_handoff_token,
    redeem_handoff_token,
)

router = APIRouter(tags=["flint-handoff"])


class FlintHandoffResponse(BaseModel):
    token: str
    expires_in: int


class FlintContextRequest(BaseModel):
    token: str = Field(min_length=1, max_length=64)


class CompanyIntelBlock(BaseModel):
    """Employer signals passed to Flint for live-session grounding."""

    mission: str = ""
    values: list[str] = Field(default_factory=list)
    culture_notes: str = ""


class FlintContextResponse(BaseModel):
    session_name: str
    session_type: str
    domain: str
    jd_text: str
    resume_summary: str
    smart_resume_session_id: str
    export_version: int
    user_id: str | None = None
    created_at: str | None = None
    # Present when the handoff originated from a saved job description
    # (extension JD-only flow). Absent for session-based handoffs.
    jd_id: str | None = None
    company_intel: CompanyIntelBlock | None = None


@router.post("/api/sessions/{session_id}/flint-handoff", response_model=FlintHandoffResponse)
@limiter.limit("30/minute")
async def create_flint_handoff(
    request: Request,
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> FlintHandoffResponse:
    """Mint a single-use token for Flint to import tailored session context."""
    session = await assert_session_owned(session_id, str(user.id))
    token, expires_in = await create_handoff_token(session, account_email=user.email)
    return FlintHandoffResponse(token=token, expires_in=expires_in)


@router.post("/api/flint/context", response_model=FlintContextResponse)
@limiter.limit("10/minute")
async def redeem_flint_context(
    request: Request,
    body: FlintContextRequest,
) -> FlintContextResponse:
    """Redeem a handoff token (single-use). No auth — token is the credential."""
    client_ip = resolve_client_ip(request) or "unknown"
    payload = await redeem_handoff_token(body.token, client_ip=client_ip)
    return FlintContextResponse.model_validate(payload)
