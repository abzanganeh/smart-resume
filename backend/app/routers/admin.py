"""Admin router (Step 35 / IMPLEMENTATION_PLAN section 8.4).

Implements every admin route under ``/api/admin/*`` from the section 6
"Admin" table, applying ``require_admin_role`` per the section 8.4.1
RBAC matrix.  State-changing routes write one ``AdminAuditLog`` row
inside the same transaction as the mutation and return its id as
``audit_log_id`` in the response body.

Public sub-routes under ``/api/admin/auth/*`` (login, 2FA verify,
accept invite) are explicitly marked with ``admin_public_route`` so
the default-deny middleware permits them through.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.dependencies.admin_auth import (
    admin_public_route,
    require_admin_role,
)
from app.limiter import limiter
from app.models.admin import (
    AdminRole,
    AdminUser,
    Announcement,
    AnnouncementAudience,
    AnnouncementSeverity,
    FeatureFlag,
    FeatureFlagVisibility,
)
from app.models.billing import (
    AdminAuditLog,
    CreditKind,
    LLMUpgradeTier,
    PlanConfig,
    PlanConfigInterval,
    RefundInitiator,
    RefundRecord,
    Subscription,
    SubscriptionStatus,
)
from app.models.export import ExportJob
from app.models.llm_config import LLMConfig, LLMProvider
from app.models.step_llm_config import StepLLMConfig
from app.models.user import (
    AuthAuditLog,
    CreditTransaction,
    User,
)
from app.services.admin_auth.audit import write_admin_audit
from app.services.admin_auth.invites import (
    create_invite,
    find_active_invite_by_token,
)
from app.services.admin_auth.tokens import (
    create_admin_2fa_setup_token,
    create_admin_challenge_token,
    create_admin_session_token,
    decode_admin_2fa_setup_token,
    decode_admin_challenge_token,
    make_ua_fingerprint,
    revoke_admin_session,
)
from app.services.admin_auth.totp import (
    admin_enroll_totp,
    admin_verify_totp,
)
from app.services.auth.client_ip import resolve_client_ip
from app.services.auth.password import (
    check_strength,
    hash_password,
    verify_password,
)
from app.services.billing.credits import grant_credit
from app.services.export.closure import (
    execute_closure,
    schedule_closure,
)

log = structlog.get_logger("admin.router")

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Request-context helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str:
    """Client IP recorded in admin audit rows and bound to admin sessions.

    Trusting ``X-Forwarded-For`` unconditionally would let a caller forge
    both the audit trail and the address its own session is pinned to.
    """
    return resolve_client_ip(request)


def _request_user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")


def _request_id(request: Request) -> str:
    return request.headers.get("x-request-id", "") or uuid.uuid4().hex


def _audit_ctx(request: Request) -> dict[str, str]:
    return {
        "ip": _client_ip(request),
        "user_agent": _request_user_agent(request),
        "request_id": _request_id(request),
    }


# ---------------------------------------------------------------------------
# Pydantic shapes
# ---------------------------------------------------------------------------


class AuditedResponse(BaseModel):
    ok: bool = True
    audit_log_id: uuid.UUID


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)


class AdminLoginChallengeResponse(BaseModel):
    next: str
    challenge_token: str
    must_change_password: bool = False
    must_enroll_2fa: bool = False


class AdminTwoFactorVerifyRequest(BaseModel):
    challenge_token: str = Field(..., min_length=1, max_length=4096)
    code: str = Field(..., min_length=1, max_length=32)


class AdminSessionResponse(BaseModel):
    access_token: str
    expires_at: datetime
    admin_id: uuid.UUID
    role: str


class AdminTwoFactorEnrollRequest(BaseModel):
    challenge_token: str = Field(..., min_length=1, max_length=4096)


class AdminTwoFactorEnrollResponse(BaseModel):
    secret: str
    provisioning_uri: str


class AdminTwoFactorEnrollVerifyResponse(BaseModel):
    ok: bool = True
    recovery_codes: list[str]
    access_token: str
    expires_at: datetime


class AdminInviteRequest(BaseModel):
    email: EmailStr
    role: str
    display_name: str = Field("", max_length=200)


class AdminInviteResponse(AuditedResponse):
    invite_id: uuid.UUID
    invite_token: str
    expires_at: datetime


class AcceptInviteRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=4096)
    password: str = Field(..., min_length=10, max_length=200)
    display_name: str = Field("", max_length=200)


class AcceptInviteResponse(BaseModel):
    setup_token: str
    must_enroll_2fa: bool = True


class AdminChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=10, max_length=200)


# ---------------------------------------------------------------------------
# /api/admin/auth/* (PUBLIC: login, 2FA setup/verify, accept-invite)
# ---------------------------------------------------------------------------


@router.post(
    "/auth/login",
    response_model=AdminLoginChallengeResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute")
@admin_public_route
async def admin_auth_login(
    request: Request,
    body: AdminLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminLoginChallengeResponse:
    """Verify credentials and decide which next-step token to issue.

    This route NEVER returns a full admin session token: an admin who
    has not yet enrolled 2FA receives an ``admin_2fa_setup`` token,
    and an admin who has 2FA receives an ``admin_challenge`` token.
    The full session is only minted by the 2FA verify endpoint.
    """
    email = body.email.strip().lower()
    admin = (
        await db.execute(select(AdminUser).where(AdminUser.email == email))
    ).scalar_one_or_none()
    if admin is None or admin.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "admin_login_failed"},
        )
    if not verify_password(body.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "admin_login_failed"},
        )
    if admin.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "admin_suspended"},
        )

    if admin.must_enroll_2fa or not admin.has_totp:
        token = create_admin_2fa_setup_token(admin.id)
        return AdminLoginChallengeResponse(
            next="enroll_2fa",
            challenge_token=token,
            must_change_password=admin.must_change_password,
            must_enroll_2fa=True,
        )

    challenge = create_admin_challenge_token(admin.id)
    return AdminLoginChallengeResponse(
        next="verify_2fa",
        challenge_token=challenge,
        must_change_password=admin.must_change_password,
        must_enroll_2fa=False,
    )


@router.post(
    "/auth/2fa/enroll",
    response_model=AdminTwoFactorEnrollResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute")
@admin_public_route
async def admin_auth_2fa_enroll(
    request: Request,
    body: AdminTwoFactorEnrollRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminTwoFactorEnrollResponse:
    """First-time TOTP enrollment.  Accepts an ``admin_2fa_setup`` token."""
    try:
        claims = decode_admin_2fa_setup_token(body.challenge_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "admin_setup_token_invalid"},
        ) from exc
    admin_id = uuid.UUID(str(claims["sub"]))
    result = await admin_enroll_totp(db, admin_id)
    return AdminTwoFactorEnrollResponse(
        secret=result.secret_b32,
        provisioning_uri=result.provisioning_uri,
    )


@router.post(
    "/auth/2fa/verify",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute")
@admin_public_route
async def admin_auth_2fa_verify(
    request: Request,
    body: AdminTwoFactorVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Verify a TOTP code and mint a full admin session token.

    Accepts either an ``admin_challenge`` token (existing 2FA) or an
    ``admin_2fa_setup`` token (first-time enrollment).  In the
    enrollment path we also return the 10 recovery codes once.
    """
    challenge = body.challenge_token
    is_setup = False
    try:
        claims = decode_admin_challenge_token(challenge)
    except Exception:
        try:
            claims = decode_admin_2fa_setup_token(challenge)
            is_setup = True
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "admin_challenge_invalid"},
            ) from exc
    admin_id = uuid.UUID(str(claims["sub"]))

    verify = await admin_verify_totp(db, admin_id, body.code)
    if not verify.ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "admin_2fa_failed"},
        )

    admin = (
        await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
    ).scalar_one_or_none()
    if admin is None or admin.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "admin_suspended"},
        )

    ip = _client_ip(request)
    ua_fp = make_ua_fingerprint(
        _request_user_agent(request), request.headers.get("accept-language", "")
    )
    issued = await create_admin_session_token(admin.id, ip, ua_fp)
    admin.last_login_at = datetime.now(timezone.utc)
    admin.last_login_ip = ip[:64]
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="admin_login",
        target_kind="admin_user",
        target_id=str(admin.id),
        after={
            "session_id": issued.session_id,
            "first_login_with_2fa": is_setup or verify.enrolled_now,
        },
        **_audit_ctx(request),
    )

    response: dict[str, Any] = {
        "access_token": issued.token,
        "expires_at": issued.expires_at.isoformat(),
        "admin_id": str(admin.id),
        "role": admin.role.value,
        "audit_log_id": str(audit_row.id),
    }
    if verify.enrolled_now and verify.recovery_codes:
        response["recovery_codes"] = verify.recovery_codes
    return response


@router.post("/auth/logout", response_model=AuditedResponse)
@limiter.limit("60/minute")
async def admin_auth_logout(
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
) -> AuditedResponse:
    claims = getattr(request.state, "admin_session_claims", None)
    if claims is not None:
        await revoke_admin_session(claims.session_id)
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="admin_logout",
        target_kind="admin_user",
        target_id=str(admin.id),
        **_audit_ctx(request),
    )
    return AuditedResponse(audit_log_id=audit_row.id)


@router.post("/auth/invite", response_model=AdminInviteResponse)
@limiter.limit("30/day")
async def admin_auth_invite(
    request: Request,
    body: AdminInviteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> AdminInviteResponse:
    """Super-admin issues an invite.  Plaintext token returned ONCE."""
    try:
        role = AdminRole(body.role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_admin_role"},
        ) from exc
    invite = await create_invite(
        db,
        email=body.email.strip().lower(),
        role=role,
        invited_by_admin_id=admin.id,
    )
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="admin_invite_created",
        target_kind="admin_invite",
        target_id=str(invite.invite_id),
        after={
            "email": body.email.strip().lower(),
            "role": role.value,
            "expires_at": invite.expires_at.isoformat(),
        },
        **_audit_ctx(request),
    )
    return AdminInviteResponse(
        invite_id=invite.invite_id,
        invite_token=invite.token,
        expires_at=invite.expires_at,
        audit_log_id=audit_row.id,
    )


@router.post("/auth/accept-invite", response_model=AcceptInviteResponse)
@limiter.limit("10/minute")
@admin_public_route
async def admin_auth_accept_invite(
    request: Request,
    body: AcceptInviteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AcceptInviteResponse:
    """Invitee sets a password and is forced into 2FA enrollment."""
    invite = await find_active_invite_by_token(db, body.token)
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invite_invalid_or_expired"},
        )
    try:
        check_strength(body.password, user_inputs=[invite.email])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "weak_password", "message": str(exc)},
        ) from exc

    existing = (
        await db.execute(select(AdminUser).where(AdminUser.email == invite.email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "admin_already_exists"},
        )

    admin = AdminUser(
        id=uuid.uuid4(),
        email=invite.email,
        display_name=body.display_name or invite.email.split("@", 1)[0],
        role=invite.role,
        password_hash=hash_password(body.password),
        must_change_password=False,
        must_enroll_2fa=True,
        created_via="invite",
        created_by_admin_id=invite.invited_by_admin_id,
    )
    db.add(admin)
    invite.accepted_at = datetime.now(timezone.utc)
    invite.accepted_admin_id = admin.id
    await db.flush()

    await write_admin_audit(
        db,
        actor_admin_id=invite.invited_by_admin_id,
        action="admin_invite_accepted",
        target_kind="admin_user",
        target_id=str(admin.id),
        after={"email": admin.email, "role": admin.role.value},
        **_audit_ctx(request),
    )

    setup_token = create_admin_2fa_setup_token(admin.id)
    return AcceptInviteResponse(setup_token=setup_token, must_enroll_2fa=True)


@router.post("/auth/change-password", response_model=AuditedResponse)
@limiter.limit("10/minute")
async def admin_auth_change_password(
    request: Request,
    body: AdminChangePasswordRequest,
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
) -> AuditedResponse:
    if not verify_password(body.current_password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "current_password_wrong"},
        )
    try:
        check_strength(body.new_password, user_inputs=[admin.email, admin.display_name])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "weak_password", "message": str(exc)},
        ) from exc
    admin.password_hash = hash_password(body.new_password)
    admin.must_change_password = False
    await db.flush()
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="admin_password_changed",
        target_kind="admin_user",
        target_id=str(admin.id),
        **_audit_ctx(request),
    )
    return AuditedResponse(audit_log_id=audit_row.id)


# ---------------------------------------------------------------------------
# Plans (PlanConfig)  -  IMPLEMENTATION_PLAN section 7.2 precedence rule
# ---------------------------------------------------------------------------


class PlanConfigOut(BaseModel):
    id: uuid.UUID
    code: str
    stripe_price_id: str
    stripe_product_id: str | None = None
    eligibility: str
    amount_cents: int
    currency: str
    interval: str
    is_active: bool
    effective_from: datetime
    effective_to: datetime | None = None
    created_by_admin_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


def _serialize_plan(row: PlanConfig) -> PlanConfigOut:
    return PlanConfigOut(
        id=row.id,
        code=row.code,
        stripe_price_id=row.stripe_price_id,
        stripe_product_id=row.stripe_product_id,
        eligibility=row.eligibility,
        amount_cents=row.amount_cents,
        currency=row.currency,
        interval=row.interval.value if hasattr(row.interval, "value") else str(row.interval),
        is_active=row.is_active,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        created_by_admin_id=row.created_by_admin_id,
        created_at=row.created_at,
    )


class PlanCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    stripe_price_id: str = Field(..., min_length=1, max_length=255)
    stripe_product_id: str | None = Field(None, max_length=255)
    eligibility: str = Field("", max_length=64)
    amount_cents: int = Field(..., ge=0)
    currency: str = Field("USD", max_length=8)
    interval: str = Field(..., min_length=1, max_length=16)


class PlanUpdateRequest(BaseModel):
    stripe_price_id: str | None = Field(None, min_length=1, max_length=255)
    stripe_product_id: str | None = Field(None, max_length=255)
    eligibility: str | None = Field(None, max_length=64)
    amount_cents: int | None = Field(None, ge=0)
    currency: str | None = Field(None, max_length=8)
    interval: str | None = Field(None, min_length=1, max_length=16)
    is_active: bool | None = None


@router.get("/plans", response_model=list[PlanConfigOut])
@limiter.limit("120/minute")
async def admin_plans_list(
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
) -> list[PlanConfigOut]:
    stmt = select(PlanConfig).order_by(PlanConfig.code, desc(PlanConfig.effective_from))
    if not include_inactive:
        stmt = stmt.where(PlanConfig.is_active.is_(True))
    rows = list((await db.execute(stmt)).scalars().all())
    return [_serialize_plan(r) for r in rows]


@router.get("/plans/history", response_model=list[PlanConfigOut])
@limiter.limit("120/minute")
async def admin_plans_history(
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
    code: str | None = None,
    limit: int = 200,
) -> list[PlanConfigOut]:
    stmt = select(PlanConfig).order_by(desc(PlanConfig.effective_from)).limit(min(limit, 500))
    if code:
        stmt = stmt.where(PlanConfig.code == code)
    rows = list((await db.execute(stmt)).scalars().all())
    return [_serialize_plan(r) for r in rows]


def _coerce_interval(value: str) -> PlanConfigInterval:
    try:
        return PlanConfigInterval(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_interval", "value": value},
        ) from exc


class PlanCreateResponse(AuditedResponse):
    plan: PlanConfigOut


@router.post("/plans", response_model=PlanCreateResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def admin_plans_create(
    request: Request,
    body: PlanCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> PlanCreateResponse:
    """Create a new PlanConfig version.

    Per IMPLEMENTATION_PLAN section 7.2: when an active row already
    exists for ``code``, set its ``effective_to`` to ``now()`` and
    insert a new row with ``effective_from = now()``.  Never delete
    history.
    """
    interval = _coerce_interval(body.interval)
    now = datetime.now(timezone.utc)
    prior = (
        await db.execute(
            select(PlanConfig)
            .where(PlanConfig.code == body.code)
            .where(PlanConfig.is_active.is_(True))
            .with_for_update()
        )
    ).scalars().all()
    before_snap: dict[str, Any] | None = None
    for r in prior:
        before_snap = before_snap or {
            "id": str(r.id),
            "stripe_price_id": r.stripe_price_id,
            "amount_cents": r.amount_cents,
            "interval": r.interval.value if hasattr(r.interval, "value") else str(r.interval),
        }
        r.is_active = False
        r.effective_to = now

    row = PlanConfig(
        id=uuid.uuid4(),
        code=body.code.strip(),
        stripe_price_id=body.stripe_price_id.strip(),
        stripe_product_id=(body.stripe_product_id or None),
        eligibility=body.eligibility,
        amount_cents=body.amount_cents,
        currency=body.currency,
        interval=interval,
        is_active=True,
        effective_from=now,
        effective_to=None,
        created_by_admin_id=admin.id,
    )
    db.add(row)
    await db.flush()

    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="plan_config_created",
        target_kind="plan_config",
        target_id=str(row.id),
        before=before_snap,
        after={
            "code": row.code,
            "stripe_price_id": row.stripe_price_id,
            "amount_cents": row.amount_cents,
            "interval": row.interval.value,
        },
        **_audit_ctx(request),
    )
    return PlanCreateResponse(
        plan=_serialize_plan(row), audit_log_id=audit_row.id
    )


@router.patch("/plans/{plan_id}", response_model=PlanCreateResponse)
@limiter.limit("30/minute")
async def admin_plans_update(
    request: Request,
    plan_id: uuid.UUID,
    body: PlanUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> PlanCreateResponse:
    row = (
        await db.execute(
            select(PlanConfig).where(PlanConfig.id == plan_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "plan_not_found"},
        )
    before_snap = {
        "stripe_price_id": row.stripe_price_id,
        "amount_cents": row.amount_cents,
        "is_active": row.is_active,
        "interval": row.interval.value,
    }
    if body.stripe_price_id is not None:
        row.stripe_price_id = body.stripe_price_id.strip()
    if body.stripe_product_id is not None:
        row.stripe_product_id = body.stripe_product_id or None
    if body.eligibility is not None:
        row.eligibility = body.eligibility
    if body.amount_cents is not None:
        row.amount_cents = body.amount_cents
    if body.currency is not None:
        row.currency = body.currency
    if body.interval is not None:
        row.interval = _coerce_interval(body.interval)
    if body.is_active is not None:
        row.is_active = body.is_active
        if body.is_active is False and row.effective_to is None:
            row.effective_to = datetime.now(timezone.utc)
    await db.flush()
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="plan_config_updated",
        target_kind="plan_config",
        target_id=str(row.id),
        before=before_snap,
        after={
            "stripe_price_id": row.stripe_price_id,
            "amount_cents": row.amount_cents,
            "is_active": row.is_active,
            "interval": row.interval.value,
        },
        **_audit_ctx(request),
    )
    return PlanCreateResponse(plan=_serialize_plan(row), audit_log_id=audit_row.id)


# ---------------------------------------------------------------------------
# LLM configs
# ---------------------------------------------------------------------------


class LLMConfigOut(BaseModel):
    id: uuid.UUID
    tier: str
    provider: str
    model_string: str
    phases_enabled: list[str]
    is_active: bool
    notes: str | None = None
    created_by_admin_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


def _serialize_llm(row: LLMConfig) -> LLMConfigOut:
    return LLMConfigOut(
        id=row.id,
        tier=row.tier.value if hasattr(row.tier, "value") else str(row.tier),
        provider=row.provider.value if hasattr(row.provider, "value") else str(row.provider),
        model_string=row.model_string,
        phases_enabled=list(row.phases_enabled or []),
        is_active=row.is_active,
        notes=row.notes,
        created_by_admin_id=row.created_by_admin_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class LLMConfigCreateRequest(BaseModel):
    tier: str = Field(..., pattern="^(standard|better|best)$")
    provider: str = Field(..., min_length=1, max_length=32)
    model_string: str = Field(..., min_length=1, max_length=255)
    phases_enabled: list[str] = Field(default_factory=list)
    notes: str | None = Field(None, max_length=500)


class LLMCreateResponse(AuditedResponse):
    llm: LLMConfigOut


@router.get("/llm", response_model=list[LLMConfigOut])
@limiter.limit("120/minute")
async def admin_llm_list(
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
) -> list[LLMConfigOut]:
    stmt = select(LLMConfig).order_by(LLMConfig.tier, desc(LLMConfig.created_at))
    if not include_inactive:
        stmt = stmt.where(LLMConfig.is_active.is_(True))
    rows = list((await db.execute(stmt)).scalars().all())
    return [_serialize_llm(r) for r in rows]


@router.get("/llm/history", response_model=list[LLMConfigOut])
@limiter.limit("120/minute")
async def admin_llm_history(
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
    tier: str | None = None,
    limit: int = 200,
) -> list[LLMConfigOut]:
    stmt = select(LLMConfig).order_by(desc(LLMConfig.created_at)).limit(min(limit, 500))
    if tier:
        try:
            tier_enum = LLMUpgradeTier(tier)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_tier"},
            ) from exc
        stmt = stmt.where(LLMConfig.tier == tier_enum)
    rows = list((await db.execute(stmt)).scalars().all())
    return [_serialize_llm(r) for r in rows]


@router.post("/llm", response_model=LLMCreateResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def admin_llm_create(
    request: Request,
    body: LLMConfigCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> LLMCreateResponse:
    """Activate a new (provider, model) pair for ``tier``.

    Same precedence rule as PlanConfig: deactivate the prior active row
    for ``tier`` and insert a new ``is_active=True`` row.  History is
    preserved for ``GET /api/admin/llm/history``.
    """
    try:
        tier_enum = LLMUpgradeTier(body.tier)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_tier"},
        ) from exc
    try:
        provider_enum = LLMProvider(body.provider)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_provider"},
        ) from exc

    prior = (
        await db.execute(
            select(LLMConfig)
            .where(LLMConfig.tier == tier_enum)
            .where(LLMConfig.is_active.is_(True))
            .with_for_update()
        )
    ).scalars().all()
    before_snap: dict[str, Any] | None = None
    for r in prior:
        before_snap = before_snap or {
            "id": str(r.id),
            "provider": r.provider.value,
            "model_string": r.model_string,
        }
        r.is_active = False

    row = LLMConfig(
        id=uuid.uuid4(),
        tier=tier_enum,
        provider=provider_enum,
        model_string=body.model_string,
        phases_enabled=list(body.phases_enabled),
        is_active=True,
        notes=body.notes,
        created_by_admin_id=admin.id,
    )
    db.add(row)
    await db.flush()

    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="llm_config_created",
        target_kind="llm_config",
        target_id=str(row.id),
        before=before_snap,
        after={
            "tier": row.tier.value,
            "provider": row.provider.value,
            "model_string": row.model_string,
        },
        **_audit_ctx(request),
    )
    return LLMCreateResponse(llm=_serialize_llm(row), audit_log_id=audit_row.id)


# ---------------------------------------------------------------------------
# Per-step LLM pins (M18 / pre-deploy cost control)
# ---------------------------------------------------------------------------


class StepLLMConfigOut(BaseModel):
    step: str
    label: str
    provider: str
    model_string: str
    source: str = Field(..., description="pin | default")
    pin_id: uuid.UUID | None = None
    is_active: bool = True
    notes: str | None = None
    has_price_row: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StepLLMConfigCreateRequest(BaseModel):
    step: str = Field(..., min_length=1, max_length=64)
    provider: str = Field(..., min_length=1, max_length=32)
    model_string: str = Field(..., min_length=1, max_length=255)
    notes: str | None = Field(None, max_length=500)


class StepLLMCreateResponse(AuditedResponse):
    step_config: StepLLMConfigOut


def _serialize_step_llm_row(
    step: str,
    *,
    provider: str,
    model_string: str,
    source: str,
    pin: StepLLMConfig | None = None,
) -> StepLLMConfigOut:
    from app.llm.model_registry import STEP_LABELS
    from app.llm.pricing import has_price_row

    return StepLLMConfigOut(
        step=step,
        label=STEP_LABELS.get(step, step),  # type: ignore[arg-type]
        provider=provider,
        model_string=model_string,
        source=source,
        pin_id=pin.id if pin else None,
        is_active=pin.is_active if pin else False,
        notes=pin.notes if pin else None,
        has_price_row=has_price_row(provider, model_string),
        created_at=pin.created_at if pin else None,
        updated_at=pin.updated_at if pin else None,
    )


async def _effective_step_pins(
    db: AsyncSession,
) -> dict[str, StepLLMConfig]:
    rows = (
        await db.execute(
            select(StepLLMConfig).where(StepLLMConfig.is_active.is_(True))
        )
    ).scalars().all()
    return {row.step: row for row in rows}


@router.get("/llm/steps", response_model=list[StepLLMConfigOut])
@limiter.limit("120/minute")
async def admin_step_llm_list(
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
) -> list[StepLLMConfigOut]:
    """Effective provider/model for every pipeline step."""
    from app.llm.model_registry import STEP_DEFAULTS, all_pipeline_steps

    active = await _effective_step_pins(db)
    out: list[StepLLMConfigOut] = []
    for step in all_pipeline_steps():
        pin = active.get(step)
        if pin is not None:
            out.append(
                _serialize_step_llm_row(
                    step,
                    provider=pin.provider.value,
                    model_string=pin.model_string,
                    source="pin",
                    pin=pin,
                )
            )
        else:
            provider, model_string = STEP_DEFAULTS[step]
            out.append(
                _serialize_step_llm_row(
                    step,
                    provider=provider,
                    model_string=model_string,
                    source="default",
                )
            )
    return out


@router.get("/llm/steps/history", response_model=list[StepLLMConfigOut])
@limiter.limit("120/minute")
async def admin_step_llm_history(
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
    step: str | None = None,
    limit: int = 200,
) -> list[StepLLMConfigOut]:
    from app.llm.model_registry import STEP_LABELS
    from app.llm.pricing import has_price_row

    stmt = (
        select(StepLLMConfig)
        .order_by(desc(StepLLMConfig.created_at))
        .limit(min(limit, 500))
    )
    if step:
        stmt = stmt.where(StepLLMConfig.step == step)
    rows = list((await db.execute(stmt)).scalars().all())
    return [
        StepLLMConfigOut(
            step=row.step,
            label=STEP_LABELS.get(row.step, row.step),  # type: ignore[arg-type]
            provider=row.provider.value,
            model_string=row.model_string,
            source="pin",
            pin_id=row.id,
            is_active=row.is_active,
            notes=row.notes,
            has_price_row=has_price_row(row.provider.value, row.model_string),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post(
    "/llm/steps",
    response_model=StepLLMCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def admin_step_llm_create(
    request: Request,
    body: StepLLMConfigCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> StepLLMCreateResponse:
    """Activate a new provider/model pin for one pipeline step."""
    from app.llm.model_registry import STEP_DEFAULTS
    from app.llm.pricing import has_price_row
    from app.services.llm.step_config import refresh_step_pin_cache

    if body.step not in STEP_DEFAULTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_step", "step": body.step},
        )
    try:
        provider_enum = LLMProvider(body.provider)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_provider"},
        ) from exc
    if not has_price_row(provider_enum.value, body.model_string):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "unpriced_model",
                "provider": provider_enum.value,
                "model_string": body.model_string,
            },
        )

    prior = (
        await db.execute(
            select(StepLLMConfig)
            .where(StepLLMConfig.step == body.step)
            .where(StepLLMConfig.is_active.is_(True))
            .with_for_update()
        )
    ).scalars().all()
    before_snap: dict[str, Any] | None = None
    for r in prior:
        before_snap = before_snap or {
            "id": str(r.id),
            "provider": r.provider.value,
            "model_string": r.model_string,
        }
        r.is_active = False

    row = StepLLMConfig(
        id=uuid.uuid4(),
        step=body.step,
        provider=provider_enum,
        model_string=body.model_string,
        is_active=True,
        notes=body.notes,
        created_by_admin_id=admin.id,
    )
    db.add(row)
    await db.flush()
    await refresh_step_pin_cache(db)

    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="step_llm_config_created",
        target_kind="step_llm_config",
        target_id=str(row.id),
        before=before_snap,
        after={
            "step": row.step,
            "provider": row.provider.value,
            "model_string": row.model_string,
        },
        **_audit_ctx(request),
    )
    serialized = _serialize_step_llm_row(
        row.step,
        provider=row.provider.value,
        model_string=row.model_string,
        source="pin",
        pin=row,
    )
    return StepLLMCreateResponse(
        step_config=serialized,
        audit_log_id=audit_row.id,
    )


# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------


class FeatureFlagOut(BaseModel):
    id: uuid.UUID
    key: str
    description: str
    enabled: bool
    rollout_percent: int
    variant: str | None = None
    allowlist_emails: list[str]
    blocklist_emails: list[str]
    visibility: str
    updated_by_admin_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


def _serialize_flag(row: FeatureFlag) -> FeatureFlagOut:
    return FeatureFlagOut(
        id=row.id,
        key=row.key,
        description=row.description,
        enabled=row.enabled,
        rollout_percent=row.rollout_percent,
        variant=row.variant,
        allowlist_emails=list(row.allowlist_emails or []),
        blocklist_emails=list(row.blocklist_emails or []),
        visibility=row.visibility.value if hasattr(row.visibility, "value") else str(row.visibility),
        updated_by_admin_id=row.updated_by_admin_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class FeatureFlagCreateRequest(BaseModel):
    key: str = Field(..., pattern=r"^[a-z][a-z0-9_]{0,79}$")
    description: str = Field("", max_length=500)
    enabled: bool = False
    rollout_percent: int = Field(100, ge=0, le=100)
    variant: str | None = Field(None, max_length=80)
    allowlist_emails: list[str] = Field(default_factory=list)
    blocklist_emails: list[str] = Field(default_factory=list)
    visibility: str = Field("public", pattern="^(public|internal)$")


class FeatureFlagUpdateRequest(BaseModel):
    description: str | None = Field(None, max_length=500)
    enabled: bool | None = None
    rollout_percent: int | None = Field(None, ge=0, le=100)
    variant: str | None = Field(None, max_length=80)
    allowlist_emails: list[str] | None = None
    blocklist_emails: list[str] | None = None
    visibility: str | None = Field(None, pattern="^(public|internal)$")


class FeatureFlagResponse(AuditedResponse):
    flag: FeatureFlagOut


@router.get("/feature-flags", response_model=list[FeatureFlagOut])
@limiter.limit("120/minute")
async def admin_feature_flags_list(
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
) -> list[FeatureFlagOut]:
    rows = list(
        (await db.execute(select(FeatureFlag).order_by(FeatureFlag.key))).scalars().all()
    )
    return [_serialize_flag(r) for r in rows]


@router.post(
    "/feature-flags",
    response_model=FeatureFlagResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def admin_feature_flags_create(
    request: Request,
    body: FeatureFlagCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> FeatureFlagResponse:
    if (
        await db.execute(select(FeatureFlag).where(FeatureFlag.key == body.key))
    ).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "feature_flag_exists"},
        )
    row = FeatureFlag(
        id=uuid.uuid4(),
        key=body.key,
        description=body.description,
        enabled=body.enabled,
        rollout_percent=body.rollout_percent,
        variant=body.variant,
        allowlist_emails=list(body.allowlist_emails or []),
        blocklist_emails=list(body.blocklist_emails or []),
        visibility=FeatureFlagVisibility(body.visibility),
        updated_by_admin_id=admin.id,
    )
    db.add(row)
    await db.flush()
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="feature_flag_created",
        target_kind="feature_flag",
        target_id=str(row.id),
        after={"key": row.key, "enabled": row.enabled},
        **_audit_ctx(request),
    )
    return FeatureFlagResponse(flag=_serialize_flag(row), audit_log_id=audit_row.id)


@router.patch(
    "/feature-flags/{key}",
    response_model=FeatureFlagResponse,
)
@limiter.limit("30/minute")
async def admin_feature_flags_update(
    request: Request,
    key: str,
    body: FeatureFlagUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> FeatureFlagResponse:
    row = (
        await db.execute(
            select(FeatureFlag).where(FeatureFlag.key == key).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "feature_flag_not_found"},
        )
    before_snap = {
        "enabled": row.enabled,
        "rollout_percent": row.rollout_percent,
        "variant": row.variant,
        "visibility": row.visibility.value,
    }
    if body.description is not None:
        row.description = body.description
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.rollout_percent is not None:
        row.rollout_percent = body.rollout_percent
    if body.variant is not None:
        row.variant = body.variant or None
    if body.allowlist_emails is not None:
        row.allowlist_emails = list(body.allowlist_emails)
    if body.blocklist_emails is not None:
        row.blocklist_emails = list(body.blocklist_emails)
    if body.visibility is not None:
        row.visibility = FeatureFlagVisibility(body.visibility)
    row.updated_at = datetime.now(timezone.utc)
    row.updated_by_admin_id = admin.id
    await db.flush()
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="feature_flag_updated",
        target_kind="feature_flag",
        target_id=str(row.id),
        before=before_snap,
        after={
            "enabled": row.enabled,
            "rollout_percent": row.rollout_percent,
            "variant": row.variant,
            "visibility": row.visibility.value,
        },
        **_audit_ctx(request),
    )
    return FeatureFlagResponse(flag=_serialize_flag(row), audit_log_id=audit_row.id)


@router.delete("/feature-flags/{key}", response_model=AuditedResponse)
@limiter.limit("30/minute")
async def admin_feature_flags_delete(
    request: Request,
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> AuditedResponse:
    row = (
        await db.execute(
            select(FeatureFlag).where(FeatureFlag.key == key).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "feature_flag_not_found"},
        )
    before_snap = {"key": row.key, "enabled": row.enabled}
    await db.delete(row)
    await db.flush()
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="feature_flag_deleted",
        target_kind="feature_flag",
        target_id=str(row.id),
        before=before_snap,
        **_audit_ctx(request),
    )
    return AuditedResponse(audit_log_id=audit_row.id)


# ---------------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------------


class AnnouncementOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    body_markdown: str
    severity: str
    audience: str
    cta_label: str | None = None
    cta_url: str | None = None
    starts_at: datetime
    ends_at: datetime
    created_by_admin_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


def _serialize_announcement(row: Announcement) -> AnnouncementOut:
    return AnnouncementOut(
        id=row.id,
        slug=row.slug,
        title=row.title,
        body_markdown=row.body_markdown,
        severity=row.severity.value if hasattr(row.severity, "value") else str(row.severity),
        audience=row.audience.value if hasattr(row.audience, "value") else str(row.audience),
        cta_label=row.cta_label,
        cta_url=row.cta_url,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        created_by_admin_id=row.created_by_admin_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class AnnouncementCreateRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=120)
    title: str = Field(..., min_length=1, max_length=200)
    body_markdown: str = Field("", max_length=20_000)
    severity: str = Field("info", pattern="^(info|warning|critical|maintenance)$")
    audience: str = Field("all", pattern="^(all|subscribed|admin)$")
    cta_label: str | None = Field(None, max_length=120)
    cta_url: str | None = Field(None, max_length=2048)
    starts_at: datetime
    ends_at: datetime


class AnnouncementUpdateRequest(BaseModel):
    title: str | None = Field(None, max_length=200)
    body_markdown: str | None = Field(None, max_length=20_000)
    severity: str | None = Field(None, pattern="^(info|warning|critical|maintenance)$")
    audience: str | None = Field(None, pattern="^(all|subscribed|admin)$")
    cta_label: str | None = Field(None, max_length=120)
    cta_url: str | None = Field(None, max_length=2048)
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class AnnouncementResponse(AuditedResponse):
    announcement: AnnouncementOut


@router.get("/announcements", response_model=list[AnnouncementOut])
@limiter.limit("120/minute")
async def admin_announcements_list(
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
) -> list[AnnouncementOut]:
    rows = list(
        (
            await db.execute(
                select(Announcement).order_by(desc(Announcement.starts_at))
            )
        )
        .scalars()
        .all()
    )
    return [_serialize_announcement(r) for r in rows]


@router.post(
    "/announcements",
    response_model=AnnouncementResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def admin_announcements_create(
    request: Request,
    body: AnnouncementCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> AnnouncementResponse:
    if body.ends_at < body.starts_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "ends_before_starts"},
        )
    if (
        await db.execute(select(Announcement).where(Announcement.slug == body.slug))
    ).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "slug_taken"},
        )
    row = Announcement(
        id=uuid.uuid4(),
        slug=body.slug.strip(),
        title=body.title,
        body_markdown=body.body_markdown,
        severity=AnnouncementSeverity(body.severity),
        audience=AnnouncementAudience(body.audience),
        cta_label=body.cta_label,
        cta_url=body.cta_url,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        created_by_admin_id=admin.id,
    )
    db.add(row)
    await db.flush()
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="announcement_created",
        target_kind="announcement",
        target_id=str(row.id),
        after={
            "slug": row.slug,
            "severity": row.severity.value,
            "audience": row.audience.value,
            "starts_at": row.starts_at.isoformat(),
            "ends_at": row.ends_at.isoformat(),
        },
        **_audit_ctx(request),
    )
    return AnnouncementResponse(
        announcement=_serialize_announcement(row), audit_log_id=audit_row.id
    )


@router.patch("/announcements/{announcement_id}", response_model=AnnouncementResponse)
@limiter.limit("30/minute")
async def admin_announcements_update(
    request: Request,
    announcement_id: uuid.UUID,
    body: AnnouncementUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> AnnouncementResponse:
    row = (
        await db.execute(
            select(Announcement).where(Announcement.id == announcement_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "announcement_not_found"},
        )
    before_snap = {
        "title": row.title,
        "severity": row.severity.value,
        "audience": row.audience.value,
        "starts_at": row.starts_at.isoformat(),
        "ends_at": row.ends_at.isoformat(),
    }
    if body.title is not None:
        row.title = body.title
    if body.body_markdown is not None:
        row.body_markdown = body.body_markdown
    if body.severity is not None:
        row.severity = AnnouncementSeverity(body.severity)
    if body.audience is not None:
        row.audience = AnnouncementAudience(body.audience)
    if body.cta_label is not None:
        row.cta_label = body.cta_label or None
    if body.cta_url is not None:
        row.cta_url = body.cta_url or None
    if body.starts_at is not None:
        row.starts_at = body.starts_at
    if body.ends_at is not None:
        row.ends_at = body.ends_at
    if row.ends_at < row.starts_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "ends_before_starts"},
        )
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="announcement_updated",
        target_kind="announcement",
        target_id=str(row.id),
        before=before_snap,
        after={
            "title": row.title,
            "severity": row.severity.value,
            "audience": row.audience.value,
        },
        **_audit_ctx(request),
    )
    return AnnouncementResponse(
        announcement=_serialize_announcement(row), audit_log_id=audit_row.id
    )


@router.delete("/announcements/{announcement_id}", response_model=AuditedResponse)
@limiter.limit("30/minute")
async def admin_announcements_delete(
    request: Request,
    announcement_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> AuditedResponse:
    row = (
        await db.execute(
            select(Announcement).where(Announcement.id == announcement_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "announcement_not_found"},
        )
    before_snap = {"slug": row.slug, "title": row.title}
    await db.delete(row)
    await db.flush()
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="announcement_deleted",
        target_kind="announcement",
        target_id=str(announcement_id),
        before=before_snap,
        **_audit_ctx(request),
    )
    return AuditedResponse(audit_log_id=audit_row.id)


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


class AdminUserSummary(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    tier: str
    suspended_at: datetime | None = None
    closure_requested_at: datetime | None = None
    created_at: datetime


class AdminUserDetail(AdminUserSummary):
    email_verified_at: datetime | None = None
    credit_balance: int
    has_totp: bool
    auth_provider: str
    blocked_companies: list[str] = []
    last_login_at: datetime | None = None
    last_login_ip: str | None = None
    signup_ip: str | None = None
    signup_abuse_review_flag: str | None = None
    suspension_reason: str | None = None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserSummary]
    total: int


@router.get("/users", response_model=AdminUserListResponse)
@limiter.limit("120/minute")
async def admin_users_list(
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
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AdminUserListResponse:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    base = select(User)
    count_stmt = select(func.count()).select_from(User)
    if q:
        like = f"%{q.strip().lower()}%"
        clause = or_(func.lower(User.email).like(like), func.lower(User.display_name).like(like))
        base = base.where(clause)
        count_stmt = count_stmt.where(clause)
    base = base.order_by(desc(User.created_at)).limit(limit).offset(offset)
    rows = list((await db.execute(base)).scalars().all())
    total = int((await db.execute(count_stmt)).scalar() or 0)
    items = [
        AdminUserSummary(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            tier=u.tier.value if hasattr(u.tier, "value") else str(u.tier),
            suspended_at=u.suspended_at,
            closure_requested_at=u.closure_requested_at,
            created_at=u.created_at,
        )
        for u in rows
    ]
    return AdminUserListResponse(items=items, total=total)


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


@router.get("/users/{user_id}", response_model=AdminUserDetail)
@limiter.limit("120/minute")
async def admin_users_detail(
    request: Request,
    user_id: uuid.UUID,
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
) -> AdminUserDetail:
    u = await _load_user_or_404(db, user_id)
    return AdminUserDetail(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        tier=u.tier.value if hasattr(u.tier, "value") else str(u.tier),
        email_verified_at=u.email_verified_at,
        credit_balance=u.credit_balance,
        has_totp=u.has_totp,
        auth_provider=u.auth_provider.value if hasattr(u.auth_provider, "value") else str(u.auth_provider),
        blocked_companies=list(u.blocked_companies or []),
        suspended_at=u.suspended_at,
        suspension_reason=u.suspension_reason,
        closure_requested_at=u.closure_requested_at,
        last_login_at=u.last_login_at,
        last_login_ip=u.last_login_ip,
        signup_ip=u.signup_ip,
        signup_abuse_review_flag=u.signup_abuse_review_flag,
        created_at=u.created_at,
    )


class AdminUserCreditsRequest(BaseModel):
    delta: int = Field(..., description="Positive grant, negative revoke")
    credit_kind: str = Field("free", pattern="^(free|better|best)$")
    reason: str = Field(..., min_length=1, max_length=200)


@router.patch("/users/{user_id}/credits", response_model=AuditedResponse)
@limiter.limit("30/minute")
async def admin_users_credits(
    request: Request,
    user_id: uuid.UUID,
    body: AdminUserCreditsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser,
        Depends(
            require_admin_role(AdminRole.super_admin, AdminRole.support_agent)
        ),
    ],
) -> AuditedResponse:
    user = await _load_user_or_404(db, user_id)
    if body.delta == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "delta_must_be_nonzero"},
        )
    kind = CreditKind(body.credit_kind)
    if body.delta > 0:
        await grant_credit(
            db,
            user_id=user.id,
            credit_kind=kind,
            delta=body.delta,
            reason=body.reason,
            admin_id=admin.id,
        )
    else:
        # Negative deltas are recorded directly so refunds / clawbacks
        # show up as a single ledger row even when the projected
        # balance is already zero.
        row = CreditTransaction(
            id=uuid.uuid4(),
            user_id=user.id,
            delta=body.delta,
            action=__import__("app.models.user", fromlist=["CreditTransactionAction"]).CreditTransactionAction.admin_revoke,
            reason=body.reason,
            credit_kind=kind,
            admin_id=admin.id,
        )
        db.add(row)
        await db.flush()
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="user_credits_adjusted",
        target_kind="user",
        target_id=str(user.id),
        after={
            "delta": body.delta,
            "credit_kind": body.credit_kind,
            "reason": body.reason,
        },
        **_audit_ctx(request),
    )
    return AuditedResponse(audit_log_id=audit_row.id)


class AdminUserSubscriptionRequest(BaseModel):
    action: str = Field(..., pattern="^(grant|revoke|reset_status)$")
    plan: str | None = Field(None, max_length=64)
    billing_cycle: str | None = Field(None, max_length=32)
    new_status: str | None = Field(None, max_length=32)
    reason: str = Field(..., min_length=1, max_length=200)


@router.patch("/users/{user_id}/subscription", response_model=AuditedResponse)
@limiter.limit("30/minute")
async def admin_users_subscription(
    request: Request,
    user_id: uuid.UUID,
    body: AdminUserSubscriptionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> AuditedResponse:
    user = await _load_user_or_404(db, user_id)
    sub = (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(desc(Subscription.created_at))
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    before_snap: dict[str, Any] = (
        {"status": sub.status.value, "plan": sub.plan.value} if sub else {}
    )
    after_snap: dict[str, Any] = {"action": body.action, "reason": body.reason}
    if body.action == "reset_status":
        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "no_subscription"},
            )
        if not body.new_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "new_status_required"},
            )
        try:
            sub.status = SubscriptionStatus(body.new_status)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_status"},
            ) from exc
        after_snap["status"] = sub.status.value
    elif body.action == "revoke":
        if sub is not None:
            sub.status = SubscriptionStatus.expired
            sub.ended_at = datetime.now(timezone.utc)
            after_snap["status"] = sub.status.value
    elif body.action == "grant":
        # Manual entitlement is a placeholder - real grants flow through
        # Stripe.  Setting status=active is the safest manual step here.
        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "no_subscription_to_modify"},
            )
        sub.status = SubscriptionStatus.active
        after_snap["status"] = sub.status.value
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="user_subscription_modified",
        target_kind="user",
        target_id=str(user.id),
        before=before_snap,
        after=after_snap,
        **_audit_ctx(request),
    )
    return AuditedResponse(audit_log_id=audit_row.id)


class AdminUserSuspendRequest(BaseModel):
    suspended: bool
    reason: str = Field(..., min_length=1, max_length=500)


@router.patch("/users/{user_id}/suspend", response_model=AuditedResponse)
@limiter.limit("30/minute")
async def admin_users_suspend(
    request: Request,
    user_id: uuid.UUID,
    body: AdminUserSuspendRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> AuditedResponse:
    user = await _load_user_or_404(db, user_id)
    before_snap = {"suspended": user.suspended_at is not None}
    if body.suspended:
        if user.suspended_at is None:
            user.suspended_at = datetime.now(timezone.utc)
        user.suspension_reason = body.reason[:500]
    else:
        user.suspended_at = None
        user.suspension_reason = None
    await db.flush()
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="user_suspended" if body.suspended else "user_unsuspended",
        target_kind="user",
        target_id=str(user.id),
        before=before_snap,
        after={"suspended": body.suspended, "reason": body.reason},
        **_audit_ctx(request),
    )
    return AuditedResponse(audit_log_id=audit_row.id)


@router.get("/users/{user_id}/transactions")
@limiter.limit("120/minute")
async def admin_users_transactions(
    request: Request,
    user_id: uuid.UUID,
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
    limit: int = 100,
) -> dict[str, Any]:
    await _load_user_or_404(db, user_id)
    rows = list(
        (
            await db.execute(
                select(CreditTransaction)
                .where(CreditTransaction.user_id == user_id)
                .order_by(desc(CreditTransaction.created_at))
                .limit(min(max(limit, 1), 500))
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": str(r.id),
                "delta": r.delta,
                "action": r.action.value if hasattr(r.action, "value") else str(r.action),
                "reason": r.reason,
                "credit_kind": r.credit_kind.value if hasattr(r.credit_kind, "value") else str(r.credit_kind),
                "stripe_event_id": r.stripe_event_id,
                "session_id": r.session_id,
                "admin_id": str(r.admin_id) if r.admin_id else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.get("/users/{user_id}/auth-log")
@limiter.limit("120/minute")
async def admin_users_auth_log(
    request: Request,
    user_id: uuid.UUID,
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
    limit: int = 100,
) -> dict[str, Any]:
    await _load_user_or_404(db, user_id)
    rows = list(
        (
            await db.execute(
                select(AuthAuditLog)
                .where(AuthAuditLog.user_id == user_id)
                .order_by(desc(AuthAuditLog.created_at))
                .limit(min(max(limit, 1), 500))
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": str(r.id),
                "event": r.event.value if hasattr(r.event, "value") else str(r.event),
                "ip": r.ip,
                "user_agent": r.user_agent,
                "metadata": r.event_metadata,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.post("/users/{user_id}/export", response_model=AuditedResponse)
@limiter.limit("30/day")
async def admin_users_export(
    request: Request,
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser,
        Depends(
            require_admin_role(AdminRole.super_admin, AdminRole.support_agent)
        ),
    ],
) -> AuditedResponse:
    user = await _load_user_or_404(db, user_id)
    job = ExportJob(id=uuid.uuid4(), user_id=user.id)
    db.add(job)
    await db.flush()
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="user_export_initiated",
        target_kind="user",
        target_id=str(user.id),
        after={"export_job_id": str(job.id)},
        **_audit_ctx(request),
    )
    # Note: actual S3 assembly is handled by the existing export
    # service.  We schedule it after the response is sent in account.py;
    # for admin we let the next scheduler tick pick it up so the audit
    # row is committed first.
    return AuditedResponse(audit_log_id=audit_row.id)


@router.post("/users/{user_id}/close", response_model=AuditedResponse)
@limiter.limit("30/day")
async def admin_users_close(
    request: Request,
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser,
        Depends(
            require_admin_role(AdminRole.super_admin, AdminRole.support_agent)
        ),
    ],
) -> AuditedResponse:
    user = await _load_user_or_404(db, user_id)
    await schedule_closure(db, user=user, cancel_subscription=True)
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="user_closure_initiated",
        target_kind="user",
        target_id=str(user.id),
        **_audit_ctx(request),
    )
    return AuditedResponse(audit_log_id=audit_row.id)


@router.post("/users/{user_id}/delete-immediately", response_model=AuditedResponse)
@limiter.limit("10/day")
async def admin_users_delete_immediately(
    request: Request,
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> AuditedResponse:
    user = await _load_user_or_404(db, user_id)
    target_id = str(user.id)
    target_email = user.email
    audit_row = await write_admin_audit(
        db,
        actor_admin_id=admin.id,
        action="user_deleted_immediately",
        target_kind="user",
        target_id=target_id,
        before={"email": target_email},
        **_audit_ctx(request),
    )
    await execute_closure(db, user_id=user.id)
    return AuditedResponse(audit_log_id=audit_row.id)


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------


class AdminRefundOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    subscription_id: uuid.UUID | None = None
    stripe_refund_id: str
    amount_usd: float
    reason: str
    initiated_by: str
    admin_id: uuid.UUID | None = None
    created_at: datetime


def _serialize_refund(r: RefundRecord) -> AdminRefundOut:
    return AdminRefundOut(
        id=r.id,
        user_id=r.user_id,
        subscription_id=r.subscription_id,
        stripe_refund_id=r.stripe_refund_id,
        amount_usd=float(r.amount_usd),
        reason=r.reason.value if hasattr(r.reason, "value") else str(r.reason),
        initiated_by=r.initiated_by.value if hasattr(r.initiated_by, "value") else str(r.initiated_by),
        admin_id=r.admin_id,
        created_at=r.created_at,
    )


@router.get("/refunds", response_model=list[AdminRefundOut])
@limiter.limit("120/minute")
async def admin_refunds_list(
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
    pending_only: bool = False,
    limit: int = 100,
) -> list[AdminRefundOut]:
    stmt = select(RefundRecord).order_by(desc(RefundRecord.created_at)).limit(min(max(limit, 1), 500))
    if pending_only:
        stmt = stmt.where(RefundRecord.stripe_refund_id.like("pending_%"))
    rows = list((await db.execute(stmt)).scalars().all())
    return [_serialize_refund(r) for r in rows]


class RefundDecisionRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    amount_usd: float | None = Field(None, ge=0)
    payment_intent: str | None = Field(None, max_length=255)
    charge: str | None = Field(None, max_length=255)
    credit_reverse_delta: int = Field(0, ge=0, le=1000)


@router.post("/refunds/{refund_id}/approve", response_model=AuditedResponse)
@limiter.limit("30/minute")
async def admin_refunds_approve(
    request: Request,
    refund_id: uuid.UUID,
    body: RefundDecisionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> AuditedResponse:
    """Approve a queued refund and execute the Stripe refund.

    Delegates to :mod:`app.services.billing.refund` so the Stripe call,
    the :class:`RefundRecord` mutation, the credit reversal, the audit
    log row, and the user notification all happen in one transaction
    (§7.6 / §18.3).
    """
    from app.services.billing import refund as refund_service
    from app.services.billing.exceptions import RefundError

    try:
        decision = await refund_service.approve_refund(
            db,
            record_id=refund_id,
            admin_id=admin.id,
            amount_usd=body.amount_usd,
            reason_note=body.reason,
            payment_intent=body.payment_intent,
            charge=body.charge,
            credit_reverse_delta=body.credit_reverse_delta,
            request_ip=_client_ip(request),
            request_user_agent=_request_user_agent(request),
        )
    except RefundError as exc:
        if exc.stage == "lookup":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "refund_not_found"},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "refund_failed",
                "stage": exc.stage,
                "message": exc.message,
            },
        ) from exc
    return AuditedResponse(audit_log_id=decision.audit_id)


@router.post("/refunds/{refund_id}/deny", response_model=AuditedResponse)
@limiter.limit("30/minute")
async def admin_refunds_deny(
    request: Request,
    refund_id: uuid.UUID,
    body: RefundDecisionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[
        AdminUser, Depends(require_admin_role(AdminRole.super_admin))
    ],
) -> AuditedResponse:
    """Deny a queued refund and email the user the denial reason."""
    from app.services.billing import refund as refund_service
    from app.services.billing.exceptions import RefundError

    try:
        decision = await refund_service.deny_refund(
            db,
            record_id=refund_id,
            admin_id=admin.id,
            reason_note=body.reason,
            request_ip=_client_ip(request),
            request_user_agent=_request_user_agent(request),
        )
    except RefundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "refund_not_found"},
        ) from exc
    return AuditedResponse(audit_log_id=decision.audit_id)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


_REPORT_ROLES = (
    AdminRole.super_admin,
    AdminRole.admin,
    AdminRole.support_agent,
    AdminRole.read_only_analyst,
)


@router.get("/reports/overview")
@limiter.limit("120/minute")
async def admin_reports_overview(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_REPORT_ROLES))],
) -> dict[str, Any]:
    user_count = int((await db.execute(select(func.count()).select_from(User))).scalar() or 0)
    sub_active = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Subscription)
                .where(
                    Subscription.status.in_(
                        [
                            SubscriptionStatus.active,
                            SubscriptionStatus.trialing,
                            SubscriptionStatus.grace,
                            SubscriptionStatus.cancel_at_period_end,
                        ]
                    )
                )
            )
        ).scalar()
        or 0
    )
    refunds_pending = int(
        (
            await db.execute(
                select(func.count())
                .select_from(RefundRecord)
                .where(RefundRecord.stripe_refund_id.like("pending_%"))
            )
        ).scalar()
        or 0
    )
    return {
        "users_total": user_count,
        "subscriptions_active": sub_active,
        "refunds_pending": refunds_pending,
    }


@router.get("/reports/registrations")
@limiter.limit("120/minute")
async def admin_reports_registrations(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_REPORT_ROLES))],
    days: int = 30,
) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=max(min(days, 365), 1))
    cnt = int(
        (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(User.created_at >= since)
            )
        ).scalar()
        or 0
    )
    return {"days": days, "registrations": cnt}


@router.get("/reports/revenue")
@limiter.limit("120/minute")
async def admin_reports_revenue(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_REPORT_ROLES))],
) -> dict[str, Any]:
    """Aggregate amount_cents across active PlanConfig rows used by
    currently-entitled subscriptions.

    This is a coarse approximation; real revenue reporting comes from
    Stripe invoices via the webhook handler.
    """
    rows = list(
        (
            await db.execute(
                select(PlanConfig.code, PlanConfig.amount_cents).where(
                    PlanConfig.is_active.is_(True)
                )
            )
        ).all()
    )
    return {
        "active_prices": [
            {"code": r[0], "amount_cents": r[1]} for r in rows
        ]
    }


@router.get("/reports/llm-costs")
@limiter.limit("120/minute")
async def admin_reports_llm_costs(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_REPORT_ROLES))],
) -> dict[str, Any]:
    rows = list(
        (
            await db.execute(
                select(LLMConfig.tier, LLMConfig.provider, LLMConfig.model_string).where(
                    LLMConfig.is_active.is_(True)
                )
            )
        ).all()
    )
    return {
        "active_tiers": [
            {
                "tier": r[0].value if hasattr(r[0], "value") else str(r[0]),
                "provider": r[1].value if hasattr(r[1], "value") else str(r[1]),
                "model_string": r[2],
            }
            for r in rows
        ]
    }


@router.get("/reports/churn")
@limiter.limit("120/minute")
async def admin_reports_churn(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_REPORT_ROLES))],
    days: int = 30,
) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=max(min(days, 365), 1))
    expired = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.ended_at >= since)
            )
        ).scalar()
        or 0
    )
    return {"days": days, "expired_subscriptions": expired}


@router.get("/reports/job-searches")
@limiter.limit("120/minute")
async def admin_reports_job_searches(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_REPORT_ROLES))],
) -> dict[str, Any]:
    """Aggregate counts from job search logs.

    The job search models live in app.models.jobs; we lazy-import to
    avoid a hard dependency in test environments without that table.
    """
    try:
        from app.models.jobs import JobSearchLog
    except ImportError:
        return {"items": []}
    cnt = int(
        (await db.execute(select(func.count()).select_from(JobSearchLog))).scalar()
        or 0
    )
    return {"job_searches_total": cnt}


@router.get("/reports/applications")
@limiter.limit("120/minute")
async def admin_reports_applications(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_REPORT_ROLES))],
) -> dict[str, Any]:
    try:
        from app.models.tracker import Application
    except ImportError:
        return {"items": []}
    cnt = int(
        (await db.execute(select(func.count()).select_from(Application))).scalar()
        or 0
    )
    return {"applications_total": cnt}


@router.get("/reports/feature-flags")
@limiter.limit("120/minute")
async def admin_reports_feature_flags(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_REPORT_ROLES))],
) -> dict[str, Any]:
    rows = list(
        (
            await db.execute(
                select(FeatureFlag.key, FeatureFlag.enabled, FeatureFlag.rollout_percent)
            )
        ).all()
    )
    return {
        "flags": [
            {"key": r[0], "enabled": r[1], "rollout_percent": r[2]} for r in rows
        ]
    }


@router.get("/reports/system-health")
@limiter.limit("120/minute")
async def admin_reports_system_health(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_admin_role(*_REPORT_ROLES))],
) -> dict[str, Any]:
    """Read-only system-health summary surfaced to admin dashboards."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    failed_webhooks = int(
        (
            await db.execute(
                select(func.count())
                .select_from(__import__("app.models.billing", fromlist=["StripeWebhookEvent"]).StripeWebhookEvent)
                .where(
                    __import__("app.models.billing", fromlist=["StripeWebhookEvent"]).StripeWebhookEvent.received_at
                    >= since
                )
                .where(
                    __import__(
                        "app.models.billing", fromlist=["StripeWebhookEvent", "StripeWebhookStatus"]
                    ).StripeWebhookEvent.status
                    == __import__(
                        "app.models.billing", fromlist=["StripeWebhookStatus"]
                    ).StripeWebhookStatus.failed
                )
            )
        ).scalar()
        or 0
    )
    return {
        "checked_at": now.isoformat(),
        "stripe_webhook_failed_24h": failed_webhooks,
    }


# ---------------------------------------------------------------------------
# Audit + auth log surfacing
# ---------------------------------------------------------------------------


@router.get("/audit-log")
@limiter.limit("120/minute")
async def admin_audit_log_list(
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
    actor_admin_id: uuid.UUID | None = None,
    target_kind: str | None = None,
    action: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Paginated audit log with the spec's filter set.

    Per IMPLEMENTATION_PLAN section 8.4.1, ``support-agent`` only sees
    their own actions.  We enforce that here regardless of the
    ``actor_admin_id`` query parameter.
    """
    stmt = select(AdminAuditLog).order_by(desc(AdminAuditLog.created_at)).limit(
        min(max(limit, 1), 500)
    )
    if admin.role == AdminRole.support_agent:
        stmt = stmt.where(AdminAuditLog.actor_admin_id == admin.id)
    elif actor_admin_id is not None:
        stmt = stmt.where(AdminAuditLog.actor_admin_id == actor_admin_id)
    if target_kind:
        stmt = stmt.where(AdminAuditLog.target_kind == target_kind)
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
    rows = list((await db.execute(stmt)).scalars().all())
    return {
        "items": [
            {
                "id": str(r.id),
                "actor_admin_id": str(r.actor_admin_id) if r.actor_admin_id else None,
                "action": r.action,
                "target_kind": r.target_kind,
                "target_id": r.target_id,
                "before": r.before_json,
                "after": r.after_json,
                "ip": r.ip,
                "user_agent": r.user_agent,
                "request_id": r.request_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.get("/auth-log")
@limiter.limit("120/minute")
async def admin_auth_log_list(
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
    user_id: uuid.UUID | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    stmt = (
        select(AuthAuditLog)
        .order_by(desc(AuthAuditLog.created_at))
        .limit(min(max(limit, 1), 500))
    )
    if user_id is not None:
        stmt = stmt.where(AuthAuditLog.user_id == user_id)
    rows = list((await db.execute(stmt)).scalars().all())
    return {
        "items": [
            {
                "id": str(r.id),
                "user_id": str(r.user_id) if r.user_id else None,
                "event": r.event.value if hasattr(r.event, "value") else str(r.event),
                "ip": r.ip,
                "user_agent": r.user_agent,
                "metadata": r.event_metadata,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


__all__ = ["router"]

from app.routers import admin_free_grant  # noqa: E402
from app.routers import admin_grants  # noqa: E402
from app.routers import admin_promo_codes  # noqa: E402
from app.routers import admin_tier_limits  # noqa: E402

router.include_router(admin_tier_limits.router)
router.include_router(admin_free_grant.router)
router.include_router(admin_grants.router)
router.include_router(admin_promo_codes.router)
