"""Admin user grants CRUD — /api/admin/grants/*"""

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
from app.models.admin_grant import AdminGrantType, AdminUserGrant
from app.models.user import User
from app.services.admin.grants import (
    InvalidGrantPayloadError,
    apply_grant_side_effects,
    validate_grant_payload,
)
from app.services.auth.client_ip import resolve_client_ip
from app.services.admin_auth.audit import write_admin_audit

router = APIRouter(tags=["admin"])

_GRANT_MUTATION_ROLES = (AdminRole.super_admin, AdminRole.support_agent)
_GRANT_READ_ROLES = (
    AdminRole.super_admin,
    AdminRole.admin,
    AdminRole.support_agent,
    AdminRole.read_only_analyst,
)


class AdminGrantOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    grant_type: AdminGrantType
    payload: dict[str, Any]
    expires_at: datetime | None = None
    created_by_admin_id: uuid.UUID | None = None
    revoked_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminGrantCreateRequest(BaseModel):
    user_id: uuid.UUID
    grant_type: AdminGrantType
    payload: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None


class AdminGrantCreateResponse(BaseModel):
    audit_log_id: uuid.UUID
    grant: AdminGrantOut


class AdminGrantRevokeResponse(BaseModel):
    audit_log_id: uuid.UUID
    grant: AdminGrantOut


def _serialize(row: AdminUserGrant) -> AdminGrantOut:
    return AdminGrantOut.model_validate(row)


async def _load_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "user_not_found"},
        )
    return user


@router.post(
    "/grants",
    response_model=AdminGrantCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def admin_grants_create(
    request: Request,
    body: AdminGrantCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_GRANT_MUTATION_ROLES))],
) -> AdminGrantCreateResponse:
    await _load_user_or_404(db, body.user_id)
    try:
        validate_grant_payload(body.grant_type, body.payload)
    except InvalidGrantPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_grant_payload", "message": str(exc)},
        ) from exc

    now = datetime.now(timezone.utc)
    grant = AdminUserGrant(
        id=uuid.uuid4(),
        user_id=body.user_id,
        grant_type=body.grant_type,
        payload=body.payload,
        expires_at=body.expires_at,
        created_by_admin_id=admin.id,
        created_at=now,
    )
    db.add(grant)
    await db.flush()

    try:
        await apply_grant_side_effects(db, grant=grant, admin_id=admin.id)
    except InvalidGrantPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_grant_payload", "message": str(exc)},
        ) from exc

    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="admin_user_grant_created",
        target_kind="admin_user_grant",
        target_id=str(grant.id),
        after={
            "user_id": str(grant.user_id),
            "grant_type": grant.grant_type.value,
            "payload": grant.payload,
        },
        ip=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        request_id=request.headers.get("x-request-id", ""),
    )
    await db.commit()
    return AdminGrantCreateResponse(
        audit_log_id=audit_row.id,
        grant=_serialize(grant),
    )


@router.get("/users/{user_id}/grants", response_model=list[AdminGrantOut])
@limiter.limit("120/minute")
async def admin_grants_list_for_user(
    request: Request,
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_GRANT_READ_ROLES))],
    include_revoked: bool = True,
) -> list[AdminGrantOut]:
    await _load_user_or_404(db, user_id)
    stmt = (
        select(AdminUserGrant)
        .where(AdminUserGrant.user_id == user_id)
        .order_by(desc(AdminUserGrant.created_at))
    )
    if not include_revoked:
        stmt = stmt.where(AdminUserGrant.revoked_at.is_(None))
    rows = list((await db.execute(stmt)).scalars().all())
    return [_serialize(r) for r in rows]


@router.patch("/grants/{grant_id}/revoke", response_model=AdminGrantRevokeResponse)
@limiter.limit("30/minute")
async def admin_grants_revoke(
    request: Request,
    grant_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_GRANT_MUTATION_ROLES))],
) -> AdminGrantRevokeResponse:
    grant = (
        await db.execute(
            select(AdminUserGrant)
            .where(AdminUserGrant.id == grant_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if grant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "grant_not_found"},
        )
    if grant.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "grant_already_revoked"},
        )

    now = datetime.now(timezone.utc)
    grant.revoked_at = now
    await db.flush()

    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="admin_user_grant_revoked",
        target_kind="admin_user_grant",
        target_id=str(grant.id),
        before={"revoked_at": None},
        after={"revoked_at": now.isoformat()},
        ip=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        request_id=request.headers.get("x-request-id", ""),
    )
    await db.commit()
    return AdminGrantRevokeResponse(
        audit_log_id=audit_row.id,
        grant=_serialize(grant),
    )


__all__ = ["router"]
