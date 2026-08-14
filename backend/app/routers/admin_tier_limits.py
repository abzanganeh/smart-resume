"""Admin tier limits CRUD — /api/admin/tier-limits/*"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.dependencies.admin_auth import require_admin_role
from app.limiter import limiter
from app.models.admin import AdminRole, AdminUser
from app.models.tier_limits import TierLimitsConfig
from app.services.admin_auth.audit import write_admin_audit
from app.services.billing.tier_limits import CANONICAL_PLAN_CODES

router = APIRouter(tags=["admin"])


class TierLimitsOut(BaseModel):
    id: uuid.UUID
    plan_code: str
    resumes_per_period: int
    cover_letters_per_period: int
    searches_per_period: int
    fit_analyses_per_period: int
    checkups_per_period: int | None = None
    story_sessions: int | None = None
    coached_sessions: int | None = None
    career_watch_companies: int
    career_watch_interval_minutes: int
    tracker_active_limit: int | None = None
    whisper_enabled: bool
    whisper_uses_per_period: int | None = None
    llm_provider: str
    llm_model_phase3: str
    soft_cap_message: str | None = None
    is_active: bool
    updated_by_admin_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AuditedTierLimitsResponse(BaseModel):
    audit_log_id: uuid.UUID
    tier_limits: TierLimitsOut


def _serialize(row: TierLimitsConfig) -> TierLimitsOut:
    return TierLimitsOut.model_validate(row)


class TierLimitsCreateRequest(BaseModel):
    plan_code: str = Field(..., min_length=1, max_length=64)
    resumes_per_period: int = Field(..., ge=0)
    cover_letters_per_period: int = Field(..., ge=0)
    searches_per_period: int = Field(..., ge=0)
    fit_analyses_per_period: int = Field(..., ge=0)
    checkups_per_period: int | None = Field(None, ge=0)
    story_sessions: int | None = Field(None, ge=0)
    coached_sessions: int | None = Field(None, ge=0)
    career_watch_companies: int = Field(..., ge=0)
    career_watch_interval_minutes: int = Field(..., ge=1)
    tracker_active_limit: int | None = Field(None, ge=0)
    whisper_enabled: bool = False
    whisper_uses_per_period: int | None = Field(None, ge=0)
    llm_provider: str = Field(..., min_length=1, max_length=64)
    llm_model_phase3: str = Field(..., min_length=1, max_length=255)
    soft_cap_message: str | None = None


class TierLimitsUpdateRequest(BaseModel):
    resumes_per_period: int | None = Field(None, ge=0)
    cover_letters_per_period: int | None = Field(None, ge=0)
    searches_per_period: int | None = Field(None, ge=0)
    fit_analyses_per_period: int | None = Field(None, ge=0)
    checkups_per_period: int | None = Field(None, ge=0)
    story_sessions: int | None = Field(None, ge=0)
    coached_sessions: int | None = Field(None, ge=0)
    career_watch_companies: int | None = Field(None, ge=0)
    career_watch_interval_minutes: int | None = Field(None, ge=1)
    tracker_active_limit: int | None = Field(None, ge=0)
    whisper_enabled: bool | None = None
    whisper_uses_per_period: int | None = Field(None, ge=0)
    llm_provider: str | None = Field(None, min_length=1, max_length=64)
    llm_model_phase3: str | None = Field(None, min_length=1, max_length=255)
    soft_cap_message: str | None = None
    is_active: bool | None = None


@router.get("/tier-limits", response_model=list[TierLimitsOut])
@limiter.limit("120/minute")
async def admin_tier_limits_list(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser,
        Depends(
            require_admin_role(
                AdminRole.super_admin,
                AdminRole.admin,
                AdminRole.support_agent,
                AdminRole.read_only_analyst,
            )
        ),
    ],
    include_inactive: bool = False,
) -> list[TierLimitsOut]:
    stmt = select(TierLimitsConfig).order_by(
        TierLimitsConfig.plan_code, desc(TierLimitsConfig.created_at)
    )
    if not include_inactive:
        stmt = stmt.where(TierLimitsConfig.is_active.is_(True))
    rows = list((await db.execute(stmt)).scalars().all())
    return [_serialize(r) for r in rows]


@router.get("/tier-limits/history", response_model=list[TierLimitsOut])
@limiter.limit("120/minute")
async def admin_tier_limits_history(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser,
        Depends(
            require_admin_role(
                AdminRole.super_admin,
                AdminRole.admin,
                AdminRole.support_agent,
                AdminRole.read_only_analyst,
            )
        ),
    ],
    plan_code: str | None = None,
    limit: int = 200,
) -> list[TierLimitsOut]:
    stmt = (
        select(TierLimitsConfig)
        .order_by(desc(TierLimitsConfig.created_at))
        .limit(min(limit, 500))
    )
    if plan_code:
        stmt = stmt.where(TierLimitsConfig.plan_code == plan_code.strip())
    rows = list((await db.execute(stmt)).scalars().all())
    return [_serialize(r) for r in rows]


@router.post(
    "/tier-limits",
    response_model=AuditedTierLimitsResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def admin_tier_limits_create(
    request: Request,
    body: TierLimitsCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(AdminRole.super_admin))],
) -> AuditedTierLimitsResponse:
    plan_code = body.plan_code.strip()
    if plan_code not in CANONICAL_PLAN_CODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_plan_code", "plan_code": plan_code},
        )

    now = datetime.now(timezone.utc)
    prior = (
        await db.execute(
            select(TierLimitsConfig)
            .where(TierLimitsConfig.plan_code == plan_code)
            .where(TierLimitsConfig.is_active.is_(True))
            .with_for_update()
        )
    ).scalars().all()
    before_snap: dict[str, Any] | None = None
    for row in prior:
        before_snap = before_snap or {"id": str(row.id), "plan_code": row.plan_code}
        row.is_active = False
        row.updated_at = now

    new_row = TierLimitsConfig(
        id=uuid.uuid4(),
        plan_code=plan_code,
        resumes_per_period=body.resumes_per_period,
        cover_letters_per_period=body.cover_letters_per_period,
        searches_per_period=body.searches_per_period,
        fit_analyses_per_period=body.fit_analyses_per_period,
        checkups_per_period=body.checkups_per_period,
        story_sessions=body.story_sessions,
        coached_sessions=body.coached_sessions,
        career_watch_companies=body.career_watch_companies,
        career_watch_interval_minutes=body.career_watch_interval_minutes,
        tracker_active_limit=body.tracker_active_limit,
        whisper_enabled=body.whisper_enabled,
        whisper_uses_per_period=body.whisper_uses_per_period,
        llm_provider=body.llm_provider.strip(),
        llm_model_phase3=body.llm_model_phase3.strip(),
        soft_cap_message=body.soft_cap_message,
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
        action="tier_limits_created",
        target_kind="tier_limits_config",
        target_id=str(new_row.id),
        before=before_snap or {},
        after={"plan_code": plan_code, "id": str(new_row.id)},
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
        request_id=request.headers.get("x-request-id", ""),
    )
    await db.commit()
    return AuditedTierLimitsResponse(
        audit_log_id=audit_row.id,
        tier_limits=_serialize(new_row),
    )


@router.patch("/tier-limits/{tier_limits_id}", response_model=AuditedTierLimitsResponse)
@limiter.limit("30/minute")
async def admin_tier_limits_update(
    request: Request,
    tier_limits_id: uuid.UUID,
    body: TierLimitsUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser,
        Depends(require_admin_role(AdminRole.super_admin, AdminRole.admin)),
    ],
) -> AuditedTierLimitsResponse:
    row = (
        await db.execute(
            select(TierLimitsConfig)
            .where(TierLimitsConfig.id == tier_limits_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "tier_limits_not_found"},
        )

    before_snap = {"plan_code": row.plan_code, "id": str(row.id)}
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(row, key, value)
    row.updated_by_admin_id = admin.id
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()

    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="tier_limits_updated",
        target_kind="tier_limits_config",
        target_id=str(row.id),
        before=before_snap,
        after=updates,
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
        request_id=request.headers.get("x-request-id", ""),
    )
    await db.commit()
    return AuditedTierLimitsResponse(
        audit_log_id=audit_row.id,
        tier_limits=_serialize(row),
    )


__all__ = ["router"]
