"""Admin promo code CRUD — /api/admin/promo-codes/*"""

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
from app.models.admin_grant import AdminGrantType
from app.models.promo_code import PromoCode
from app.services.admin.grants import InvalidGrantPayloadError, validate_grant_payload
from app.services.admin_auth.audit import write_admin_audit
from app.services.billing.promo import normalize_promo_code

router = APIRouter(tags=["admin"])

_PROMO_MUTATION_ROLES = (AdminRole.super_admin, AdminRole.admin)
_PROMO_READ_ROLES = (
    AdminRole.super_admin,
    AdminRole.admin,
    AdminRole.support_agent,
    AdminRole.read_only_analyst,
)


class PromoCodeOut(BaseModel):
    id: uuid.UUID
    code: str
    grant_type: AdminGrantType
    payload: dict[str, Any]
    max_redemptions: int | None = None
    redemption_count: int
    expires_at: datetime | None = None
    is_active: bool
    created_by_admin_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PromoCodeCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    grant_type: AdminGrantType
    payload: dict[str, Any] = Field(default_factory=dict)
    max_redemptions: int | None = Field(None, ge=1)
    expires_at: datetime | None = None


class PromoCodeUpdateRequest(BaseModel):
    max_redemptions: int | None = Field(None, ge=1)
    expires_at: datetime | None = None
    is_active: bool | None = None


class PromoCodeCreateResponse(BaseModel):
    audit_log_id: uuid.UUID
    promo_code: PromoCodeOut


class PromoCodeUpdateResponse(BaseModel):
    audit_log_id: uuid.UUID
    promo_code: PromoCodeOut


def _serialize(row: PromoCode) -> PromoCodeOut:
    return PromoCodeOut.model_validate(row)


@router.get("/promo-codes", response_model=list[PromoCodeOut])
@limiter.limit("120/minute")
async def admin_promo_codes_list(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_PROMO_READ_ROLES))],
    include_inactive: bool = False,
) -> list[PromoCodeOut]:
    stmt = select(PromoCode).order_by(desc(PromoCode.created_at))
    if not include_inactive:
        stmt = stmt.where(PromoCode.is_active.is_(True))
    rows = list((await db.execute(stmt)).scalars().all())
    return [_serialize(r) for r in rows]


@router.post(
    "/promo-codes",
    response_model=PromoCodeCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def admin_promo_codes_create(
    request: Request,
    body: PromoCodeCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_PROMO_MUTATION_ROLES))],
) -> PromoCodeCreateResponse:
    normalized = normalize_promo_code(body.code)
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_promo_code"},
        )
    try:
        validate_grant_payload(body.grant_type, body.payload)
    except InvalidGrantPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_grant_payload", "message": str(exc)},
        ) from exc

    existing = (
        await db.execute(select(PromoCode).where(PromoCode.code == normalized))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "promo_code_exists"},
        )

    now = datetime.now(timezone.utc)
    row = PromoCode(
        id=uuid.uuid4(),
        code=normalized,
        grant_type=body.grant_type,
        payload=body.payload,
        max_redemptions=body.max_redemptions,
        redemption_count=0,
        expires_at=body.expires_at,
        is_active=True,
        created_by_admin_id=admin.id,
        created_at=now,
    )
    db.add(row)
    await db.flush()

    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="promo_code_created",
        target_kind="promo_code",
        target_id=str(row.id),
        after={
            "code": row.code,
            "grant_type": row.grant_type.value,
            "max_redemptions": row.max_redemptions,
        },
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
        request_id=request.headers.get("x-request-id", ""),
    )
    await db.commit()
    return PromoCodeCreateResponse(
        audit_log_id=audit_row.id,
        promo_code=_serialize(row),
    )


@router.patch(
    "/promo-codes/{promo_code_id}",
    response_model=PromoCodeUpdateResponse,
)
@limiter.limit("30/minute")
async def admin_promo_codes_update(
    request: Request,
    promo_code_id: uuid.UUID,
    body: PromoCodeUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_PROMO_MUTATION_ROLES))],
) -> PromoCodeUpdateResponse:
    row = (
        await db.execute(
            select(PromoCode).where(PromoCode.id == promo_code_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "promo_code_not_found"},
        )

    before_snap = {
        "max_redemptions": row.max_redemptions,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "is_active": row.is_active,
    }
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(row, key, value)
    await db.flush()

    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="promo_code_updated",
        target_kind="promo_code",
        target_id=str(row.id),
        before=before_snap,
        after=updates,
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
        request_id=request.headers.get("x-request-id", ""),
    )
    await db.commit()
    return PromoCodeUpdateResponse(
        audit_log_id=audit_row.id,
        promo_code=_serialize(row),
    )


__all__ = ["router"]
