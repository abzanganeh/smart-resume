"""Admin tier step LLM pins — /api/admin/llm/tier-steps/*"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.dependencies.admin_auth import require_admin_role
from app.limiter import limiter
from app.models.admin import AdminRole, AdminUser
from app.models.llm_config import LLMProvider
from app.models.step_llm_config import StepLLMConfig
from app.models.tier_step_llm_config import TierStepLLMConfig
from app.services.admin_auth.audit import write_admin_audit
from app.services.billing.tier_limits import CANONICAL_PLAN_CODES
from app.services.llm.step_config import refresh_llm_pin_caches

router = APIRouter(tags=["admin"])


def _audit_ctx(request: Request) -> dict[str, str]:
    from app.services.auth.client_ip import resolve_client_ip

    return {
        "ip": resolve_client_ip(request) or "unknown",
        "user_agent": request.headers.get("user-agent", ""),
    }


class TierStepLLMConfigOut(BaseModel):
    plan_code: str
    step: str
    label: str
    provider: str
    model_string: str
    source: str = Field(..., description="tier_pin | global_pin | default")
    pin_id: uuid.UUID | None = None
    is_active: bool = True
    notes: str | None = None
    has_price_row: bool = True
    editable: bool = True
    lock_reason: str | None = Field(
        None, description="inherited_client | global_only when not editable"
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TierStepLLMConfigCreateRequest(BaseModel):
    plan_codes: list[str] = Field(..., min_length=1)
    step: str = Field(..., min_length=1, max_length=64)
    provider: str = Field(..., min_length=1, max_length=32)
    model_string: str = Field(..., min_length=1, max_length=255)
    notes: str | None = Field(None, max_length=500)


class TierStepLLMCreateResponse(BaseModel):
    step_configs: list[TierStepLLMConfigOut]
    audit_log_id: uuid.UUID


class TierStepLLMConfigBulkRequest(BaseModel):
    plan_code: str = Field(..., min_length=1, max_length=64)
    steps: list[str] = Field(..., min_length=1, max_length=22)
    provider: str = Field(..., min_length=1, max_length=32)
    model_string: str = Field(..., min_length=1, max_length=255)
    notes: str | None = Field(None, max_length=500)


class TierStepLLMConfigBulkResponse(BaseModel):
    step_configs: list[TierStepLLMConfigOut]
    audit_log_id: uuid.UUID


async def _upsert_tier_step_pin(
    db: AsyncSession,
    *,
    plan_code: str,
    step: str,
    provider: LLMProvider,
    model_string: str,
    notes: str | None,
    admin: AdminUser,
) -> tuple[TierStepLLMConfig, dict[str, Any] | None]:
    """Deactivate prior active pin and insert a new active row for plan_code × step."""
    prior = (
        await db.execute(
            select(TierStepLLMConfig)
            .where(TierStepLLMConfig.plan_code == plan_code)
            .where(TierStepLLMConfig.step == step)
            .where(TierStepLLMConfig.is_active.is_(True))
            .with_for_update()
        )
    ).scalars().all()
    before_snap: dict[str, Any] | None = None
    for row in prior:
        if before_snap is None:
            before_snap = {
                "id": str(row.id),
                "provider": row.provider.value,
                "model_string": row.model_string,
            }
        row.is_active = False

    created = TierStepLLMConfig(
        id=uuid.uuid4(),
        plan_code=plan_code,
        step=step,
        provider=provider,
        model_string=model_string,
        is_active=True,
        notes=notes,
        created_by_admin_id=admin.id,
    )
    db.add(created)
    return created, before_snap


def _serialize_tier_step_row(
    plan_code: str,
    step: str,
    *,
    provider: str,
    model_string: str,
    source: str,
    pin: TierStepLLMConfig | None = None,
) -> TierStepLLMConfigOut:
    from app.llm.model_registry import STEP_LABELS, tier_step_is_editable, tier_step_lock_reason
    from app.llm.pricing import has_price_row

    lock_reason = tier_step_lock_reason(step)
    return TierStepLLMConfigOut(
        plan_code=plan_code,
        step=step,
        label=STEP_LABELS.get(step, step),  # type: ignore[arg-type]
        provider=provider,
        model_string=model_string,
        source=source,
        pin_id=pin.id if pin else None,
        is_active=pin.is_active if pin else False,
        notes=pin.notes if pin else None,
        has_price_row=has_price_row(provider, model_string),
        editable=tier_step_is_editable(step),
        lock_reason=lock_reason,
        created_at=pin.created_at if pin else None,
        updated_at=pin.updated_at if pin else None,
    )


async def _effective_global_pins(db: AsyncSession) -> dict[str, StepLLMConfig]:
    rows = (
        await db.execute(
            select(StepLLMConfig).where(StepLLMConfig.is_active.is_(True))
        )
    ).scalars().all()
    return {row.step: row for row in rows}


async def _effective_tier_pins(
    db: AsyncSession,
    plan_code: str,
) -> dict[str, TierStepLLMConfig]:
    rows = (
        await db.execute(
            select(TierStepLLMConfig)
            .where(TierStepLLMConfig.plan_code == plan_code)
            .where(TierStepLLMConfig.is_active.is_(True))
        )
    ).scalars().all()
    return {row.step: row for row in rows}


@router.get("/llm/tier-steps", response_model=list[TierStepLLMConfigOut])
@limiter.limit("120/minute")
async def admin_tier_step_llm_list(
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
    plan_code: str,
) -> list[TierStepLLMConfigOut]:
    """Effective provider/model for every pipeline step under one plan_code."""
    from app.llm.model_registry import STEP_DEFAULTS, all_pipeline_steps

    if plan_code not in CANONICAL_PLAN_CODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_plan_code", "plan_code": plan_code},
        )

    tier_active = await _effective_tier_pins(db, plan_code)
    global_active = await _effective_global_pins(db)
    out: list[TierStepLLMConfigOut] = []
    for step in all_pipeline_steps():
        tier_pin = tier_active.get(step)
        if tier_pin is not None:
            out.append(
                _serialize_tier_step_row(
                    plan_code,
                    step,
                    provider=tier_pin.provider.value,
                    model_string=tier_pin.model_string,
                    source="tier_pin",
                    pin=tier_pin,
                )
            )
            continue
        global_pin = global_active.get(step)
        if global_pin is not None:
            out.append(
                _serialize_tier_step_row(
                    plan_code,
                    step,
                    provider=global_pin.provider.value,
                    model_string=global_pin.model_string,
                    source="global_pin",
                )
            )
            continue
        provider, model_string = STEP_DEFAULTS[step]
        out.append(
            _serialize_tier_step_row(
                plan_code,
                step,
                provider=provider,
                model_string=model_string,
                source="default",
            )
        )
    return out


@router.get("/llm/tier-steps/history", response_model=list[TierStepLLMConfigOut])
@limiter.limit("120/minute")
async def admin_tier_step_llm_history(
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
    step: str | None = None,
    limit: int = 200,
) -> list[TierStepLLMConfigOut]:
    from app.llm.model_registry import STEP_LABELS, tier_step_is_editable, tier_step_lock_reason
    from app.llm.pricing import has_price_row

    stmt = (
        select(TierStepLLMConfig)
        .order_by(desc(TierStepLLMConfig.created_at))
        .limit(min(limit, 500))
    )
    if plan_code:
        stmt = stmt.where(TierStepLLMConfig.plan_code == plan_code)
    if step:
        stmt = stmt.where(TierStepLLMConfig.step == step)
    rows = list((await db.execute(stmt)).scalars().all())
    return [
        TierStepLLMConfigOut(
            plan_code=row.plan_code,
            step=row.step,
            label=STEP_LABELS.get(row.step, row.step),  # type: ignore[arg-type]
            provider=row.provider.value,
            model_string=row.model_string,
            source="tier_pin",
            pin_id=row.id,
            is_active=row.is_active,
            notes=row.notes,
            has_price_row=has_price_row(row.provider.value, row.model_string),
            editable=tier_step_is_editable(row.step),
            lock_reason=tier_step_lock_reason(row.step),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post(
    "/llm/tier-steps",
    response_model=TierStepLLMCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def admin_tier_step_llm_create(
    request: Request,
    body: TierStepLLMConfigCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> TierStepLLMCreateResponse:
    """Activate a new provider/model pin for plan_code(s) × one pipeline step."""
    from app.llm.model_registry import STEP_DEFAULTS, tier_step_lock_reason

    if body.step not in STEP_DEFAULTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_step", "step": body.step},
        )
    lock_reason = tier_step_lock_reason(body.step)
    if lock_reason == "inherited_client":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "inherited_client_step", "step": body.step},
        )
    if lock_reason == "global_only":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "global_only_step", "step": body.step},
        )
    plan_codes = [code.strip() for code in body.plan_codes]
    invalid = [code for code in plan_codes if code not in CANONICAL_PLAN_CODES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_plan_code", "plan_codes": invalid},
        )
    try:
        provider_enum = LLMProvider(body.provider)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_provider"},
        ) from exc
    from app.llm.pricing import has_price_row

    if not has_price_row(provider_enum.value, body.model_string):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "unpriced_model",
                "provider": provider_enum.value,
                "model_string": body.model_string,
            },
        )

    created_rows: list[TierStepLLMConfig] = []
    before_snaps: dict[str, Any] = {}
    for plan_code in plan_codes:
        row, before_snap = await _upsert_tier_step_pin(
            db,
            plan_code=plan_code,
            step=body.step,
            provider=provider_enum,
            model_string=body.model_string,
            notes=body.notes,
            admin=admin,
        )
        if before_snap is not None:
            before_snaps[f"{plan_code}:{body.step}"] = before_snap
        created_rows.append(row)

    await db.flush()
    await refresh_llm_pin_caches(db)

    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="tier_step_llm_config_created",
        target_kind="tier_step_llm_config",
        target_id=str(created_rows[0].id) if created_rows else None,
        before=before_snaps or None,
        after={
            "plan_codes": plan_codes,
            "step": body.step,
            "provider": provider_enum.value,
            "model_string": body.model_string,
        },
        **_audit_ctx(request),
    )
    serialized = [
        _serialize_tier_step_row(
            row.plan_code,
            row.step,
            provider=row.provider.value,
            model_string=row.model_string,
            source="tier_pin",
            pin=row,
        )
        for row in created_rows
    ]
    return TierStepLLMCreateResponse(
        step_configs=serialized,
        audit_log_id=audit_row.id,
    )


def _collect_bulk_step_validation_errors(steps: list[str]) -> list[dict[str, Any]]:
    from app.llm.model_registry import STEP_DEFAULTS, tier_step_lock_reason

    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for step in steps:
        if step in seen:
            errors.append({"step": step, "code": "duplicate_step"})
            continue
        seen.add(step)
        if step not in STEP_DEFAULTS:
            errors.append({"step": step, "code": "invalid_step"})
            continue
        lock_reason = tier_step_lock_reason(step)
        if lock_reason == "inherited_client":
            errors.append({"step": step, "code": "inherited_client_step"})
        elif lock_reason == "global_only":
            errors.append({"step": step, "code": "global_only_step"})
    return errors


@router.post(
    "/llm/tier-steps/bulk",
    response_model=TierStepLLMConfigBulkResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def admin_tier_step_llm_bulk_create(
    request: Request,
    body: TierStepLLMConfigBulkRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> TierStepLLMConfigBulkResponse:
    """Activate provider/model pins for one plan_code × multiple pipeline steps."""
    plan_code = body.plan_code.strip()
    if plan_code not in CANONICAL_PLAN_CODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_plan_code", "plan_code": plan_code},
        )
    try:
        provider_enum = LLMProvider(body.provider)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_provider"},
        ) from exc
    from app.llm.pricing import has_price_row

    if not has_price_row(provider_enum.value, body.model_string):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "unpriced_model",
                "provider": provider_enum.value,
                "model_string": body.model_string,
            },
        )

    step_errors = _collect_bulk_step_validation_errors(body.steps)
    if step_errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "bulk_validation_failed", "errors": step_errors},
        )

    created_rows: list[TierStepLLMConfig] = []
    before_snaps: dict[str, Any] = {}
    for step in body.steps:
        row, before_snap = await _upsert_tier_step_pin(
            db,
            plan_code=plan_code,
            step=step,
            provider=provider_enum,
            model_string=body.model_string,
            notes=body.notes,
            admin=admin,
        )
        if before_snap is not None:
            before_snaps[f"{plan_code}:{step}"] = before_snap
        created_rows.append(row)

    await db.flush()
    await refresh_llm_pin_caches(db)

    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="tier_step_llm_config_bulk_created",
        target_kind="tier_step_llm_config",
        target_id=str(created_rows[0].id) if created_rows else None,
        before=before_snaps or None,
        after={
            "plan_code": plan_code,
            "steps": body.steps,
            "provider": provider_enum.value,
            "model_string": body.model_string,
        },
        **_audit_ctx(request),
    )
    serialized = [
        _serialize_tier_step_row(
            row.plan_code,
            row.step,
            provider=row.provider.value,
            model_string=row.model_string,
            source="tier_pin",
            pin=row,
        )
        for row in created_rows
    ]
    return TierStepLLMConfigBulkResponse(
        step_configs=serialized,
        audit_log_id=audit_row.id,
    )


@router.delete(
    "/llm/tier-steps/{plan_code}/{step}",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("30/minute")
async def admin_tier_step_llm_delete(
    request: Request,
    plan_code: str,
    step: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> dict[str, str]:
    """Deactivate the active tier pin for plan_code × step (inherit global/default)."""
    if plan_code not in CANONICAL_PLAN_CODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_plan_code", "plan_code": plan_code},
        )

    prior = (
        await db.execute(
            select(TierStepLLMConfig)
            .where(TierStepLLMConfig.plan_code == plan_code)
            .where(TierStepLLMConfig.step == step)
            .where(TierStepLLMConfig.is_active.is_(True))
            .with_for_update()
        )
    ).scalars().all()
    if not prior:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "tier_pin_not_found", "plan_code": plan_code, "step": step},
        )

    before_snap = {
        "id": str(prior[0].id),
        "provider": prior[0].provider.value,
        "model_string": prior[0].model_string,
    }
    for row in prior:
        row.is_active = False

    await db.flush()
    await refresh_llm_pin_caches(db)

    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="tier_step_llm_config_deleted",
        target_kind="tier_step_llm_config",
        target_id=before_snap["id"],
        before=before_snap,
        after=None,
        **_audit_ctx(request),
    )
    return {"status": "deleted", "audit_log_id": str(audit_row.id)}
