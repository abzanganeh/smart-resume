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
from app.models.promo_code import PromoCode, PromoRedemption
from app.models.user import User
from app.services.admin.grants import InvalidGrantPayloadError, validate_grant_payload
from app.services.auth.client_ip import resolve_client_ip
from app.services.admin_auth.audit import write_admin_audit
from app.services.billing.promo import normalize_promo_code
from app.services.billing.promo_offers import (
    offer_summary_for_promo,
    remaining_redemptions,
)

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
    is_redeemable: bool
    offer_summary: str
    remaining_redemptions: int | None = None
    created_by_admin_id: uuid.UUID | None = None
    restricted_user_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PromoCodeCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    grant_type: AdminGrantType
    payload: dict[str, Any] = Field(default_factory=dict)
    max_redemptions: int | None = Field(None, ge=1)
    expires_at: datetime | None = None
    restricted_user_id: uuid.UUID | None = None


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


class PromoRedemptionOut(BaseModel):
    id: uuid.UUID
    promo_code_id: uuid.UUID
    user_id: uuid.UUID
    redeemed_at: datetime

    model_config = {"from_attributes": True}


def _serialize(row: PromoCode) -> PromoCodeOut:
    return PromoCodeOut(
        id=row.id,
        code=row.code,
        grant_type=row.grant_type,
        payload=dict(row.payload or {}),
        max_redemptions=row.max_redemptions,
        redemption_count=row.redemption_count,
        expires_at=row.expires_at,
        is_active=row.is_active,
        is_redeemable=row.is_redeemable,
        offer_summary=offer_summary_for_promo(row),
        remaining_redemptions=remaining_redemptions(row),
        created_by_admin_id=row.created_by_admin_id,
        restricted_user_id=row.restricted_user_id,
        created_at=row.created_at,
    )


@router.get("/promo-codes", response_model=list[PromoCodeOut])
@limiter.limit("120/minute")
async def admin_promo_codes_list(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_PROMO_READ_ROLES))],
    include_inactive: bool = False,
    grant_type: AdminGrantType | None = None,
) -> list[PromoCodeOut]:
    stmt = select(PromoCode).order_by(desc(PromoCode.created_at))
    if not include_inactive:
        stmt = stmt.where(PromoCode.is_active.is_(True))
    if grant_type is not None:
        stmt = stmt.where(PromoCode.grant_type == grant_type)
    rows = list((await db.execute(stmt)).scalars().all())
    return [_serialize(r) for r in rows]


@router.get("/promo-codes/{promo_code_id}", response_model=PromoCodeOut)
@limiter.limit("120/minute")
async def admin_promo_codes_get(
    request: Request,
    promo_code_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_PROMO_READ_ROLES))],
) -> PromoCodeOut:
    row = await _load_promo_or_404(db, promo_code_id)
    return _serialize(row)


async def _load_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "user_not_found"},
        )
    return user


async def _load_promo_or_404(db: AsyncSession, promo_code_id: uuid.UUID) -> PromoCode:
    promo = await db.get(PromoCode, promo_code_id)
    if promo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "promo_code_not_found"},
        )
    return promo


@router.get(
    "/promo-codes/{promo_code_id}/redemptions",
    response_model=list[PromoRedemptionOut],
)
@limiter.limit("120/minute")
async def admin_promo_code_redemptions(
    request: Request,
    promo_code_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_PROMO_READ_ROLES))],
) -> list[PromoRedemptionOut]:
    await _load_promo_or_404(db, promo_code_id)
    rows = list(
        (
            await db.execute(
                select(PromoRedemption)
                .where(PromoRedemption.promo_code_id == promo_code_id)
                .order_by(desc(PromoRedemption.redeemed_at))
            )
        ).scalars().all()
    )
    return [PromoRedemptionOut.model_validate(r) for r in rows]


@router.get(
    "/users/{user_id}/promo-codes",
    response_model=list[PromoCodeOut],
)
@limiter.limit("120/minute")
async def admin_user_promo_codes(
    request: Request,
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_PROMO_READ_ROLES))],
) -> list[PromoCodeOut]:
    await _load_user_or_404(db, user_id)
    rows = list(
        (
            await db.execute(
                select(PromoCode)
                .where(PromoCode.restricted_user_id == user_id)
                .order_by(desc(PromoCode.created_at))
            )
        ).scalars().all()
    )
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

    if body.restricted_user_id is not None:
        target_user = await db.get(User, body.restricted_user_id)
        if target_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "user_not_found"},
            )

    max_redemptions = body.max_redemptions
    if body.restricted_user_id is not None and max_redemptions is None:
        max_redemptions = 1

    now = datetime.now(timezone.utc)
    row = PromoCode(
        id=uuid.uuid4(),
        code=normalized,
        grant_type=body.grant_type,
        payload=body.payload,
        max_redemptions=max_redemptions,
        redemption_count=0,
        expires_at=body.expires_at,
        is_active=True,
        created_by_admin_id=admin.id,
        restricted_user_id=body.restricted_user_id,
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
            "restricted_user_id": str(row.restricted_user_id)
            if row.restricted_user_id
            else None,
        },
        ip=resolve_client_ip(request),
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
        ip=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        request_id=request.headers.get("x-request-id", ""),
    )
    await db.commit()
    return PromoCodeUpdateResponse(
        audit_log_id=audit_row.id,
        promo_code=_serialize(row),
    )


__all__ = ["router"]
