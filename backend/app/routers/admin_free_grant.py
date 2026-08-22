"""Admin free-plan starting credits — /api/admin/credits/free-grant"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.dependencies.admin_auth import require_admin_role
from app.limiter import limiter
from app.models.admin import AdminRole, AdminUser
from app.models.tier_limits import TierLimitsConfig
from app.services.auth.client_ip import resolve_client_ip
from app.services.admin_auth.audit import write_admin_audit
from app.services.billing.tier_limits import seed_row_for_plan
from app.services.billing.tier_limits_lookup import registration_grant_credits

router = APIRouter(tags=["admin"])

_MUTATION_ROLES = (AdminRole.super_admin, AdminRole.admin)
_READ_ROLES = (
    AdminRole.super_admin,
    AdminRole.admin,
    AdminRole.support_agent,
    AdminRole.read_only_analyst,
)


class FreeGrantOut(BaseModel):
    amount: int


class FreeGrantPatchRequest(BaseModel):
    amount: int = Field(..., ge=0)


class FreeGrantPatchResponse(BaseModel):
    audit_log_id: uuid.UUID
    free_grant: FreeGrantOut


async def _current_free_template(
    db: AsyncSession,
) -> dict[str, Any]:
    row = (
        await db.execute(
            select(TierLimitsConfig)
            .where(TierLimitsConfig.plan_code == "free")
            .where(TierLimitsConfig.is_active.is_(True))
            .order_by(TierLimitsConfig.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is not None:
        return {
            "resumes_per_period": row.resumes_per_period,
            "cover_letters_per_period": row.cover_letters_per_period,
            "searches_per_period": row.searches_per_period,
            "fit_analyses_per_period": row.fit_analyses_per_period,
            "checkups_per_period": row.checkups_per_period,
            "story_sessions": row.story_sessions,
            "coached_sessions": row.coached_sessions,
            "career_watch_companies": row.career_watch_companies,
            "career_watch_interval_minutes": row.career_watch_interval_minutes,
            "tracker_active_limit": row.tracker_active_limit,
            "whisper_enabled": row.whisper_enabled,
            "whisper_uses_per_period": row.whisper_uses_per_period,
            "llm_provider": row.llm_provider,
            "llm_model_phase3": row.llm_model_phase3,
            "soft_cap_message": row.soft_cap_message,
        }
    seed = seed_row_for_plan("free")
    if seed is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "free_tier_seed_missing"},
        )
    return {k: v for k, v in seed.items() if k != "plan_code"}


@router.get("/credits/free-grant", response_model=FreeGrantOut)
@limiter.limit("120/minute")
async def admin_free_grant_get(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_READ_ROLES))],
) -> FreeGrantOut:
    amount = await registration_grant_credits(db)
    return FreeGrantOut(amount=amount)


@router.patch("/credits/free-grant", response_model=FreeGrantPatchResponse)
@limiter.limit("30/minute")
async def admin_free_grant_patch(
    request: Request,
    body: FreeGrantPatchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_MUTATION_ROLES))],
) -> FreeGrantPatchResponse:
    template = await _current_free_template(db)
    before_amount = template["resumes_per_period"]

    now = datetime.now(timezone.utc)
    prior = (
        await db.execute(
            select(TierLimitsConfig)
            .where(TierLimitsConfig.plan_code == "free")
            .where(TierLimitsConfig.is_active.is_(True))
            .with_for_update()
        )
    ).scalars().all()
    for row in prior:
        row.is_active = False
        row.updated_at = now

    new_row = TierLimitsConfig(
        id=uuid.uuid4(),
        plan_code="free",
        resumes_per_period=body.amount,
        cover_letters_per_period=body.amount,
        searches_per_period=template["searches_per_period"],
        fit_analyses_per_period=template["fit_analyses_per_period"],
        checkups_per_period=template["checkups_per_period"],
        story_sessions=template["story_sessions"],
        coached_sessions=template["coached_sessions"],
        career_watch_companies=template["career_watch_companies"],
        career_watch_interval_minutes=template["career_watch_interval_minutes"],
        tracker_active_limit=template["tracker_active_limit"],
        whisper_enabled=template["whisper_enabled"],
        whisper_uses_per_period=template["whisper_uses_per_period"],
        llm_provider=template["llm_provider"],
        llm_model_phase3=template["llm_model_phase3"],
        soft_cap_message=template["soft_cap_message"],
        is_active=True,
        updated_by_admin_id=admin.id,
        created_at=now,
        updated_at=now,
    )
    db.add(new_row)
    await db.flush()

    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="free_grant_updated",
        target_kind="tier_limits_config",
        target_id=str(new_row.id),
        before={"amount": before_amount},
        after={"amount": body.amount},
        ip=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        request_id=request.headers.get("x-request-id", ""),
    )
    await db.commit()
    return FreeGrantPatchResponse(
        audit_log_id=audit_row.id,
        free_grant=FreeGrantOut(amount=body.amount),
    )


__all__ = ["router"]
