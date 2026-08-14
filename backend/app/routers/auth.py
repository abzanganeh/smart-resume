"""User-facing auth router.

Implements the 15 routes from IMPLEMENTATION_PLAN §6 "Auth" table plus
the security rules in §8.2 / §18.2 of SYSTEM_DESIGN_PHASE_2:

- ``user_id`` is always derived from the verified access JWT.
- DB queries are scoped by ``user_id``.
- Rate limits applied via slowapi.
- ``AuthAuditLog`` rows are written for every security-relevant event.
- Refresh tokens ride in ``Secure HttpOnly SameSite=Lax`` cookies in any
  production-grade environment; ``Secure`` drops in local dev only.

Note: route handlers stay thin — heavy lifting lives in
``app.services.auth.*``.  The router exists to translate service
errors into HTTP shapes and to wire the slowapi limiter onto the path.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import is_production_grade, settings
from app.db.engine import get_db
from app.limiter import limiter
from app.models.billing import CreditKind
from app.models.user import (
    AuthAuditEvent,
    AuthProvider,
    CreditTransaction,
    CreditTransactionAction,
    RefreshToken,
    User,
    UserTier,
)
from app.services.billing.credits import get_balance
from app.services.billing.tier_limits_lookup import registration_grant_credits
from app.services.auth import session as redis_session
from app.services.auth.audit import is_account_locked, record_auth_event
from app.services.auth.dependencies import CLOSURE_HEADER, get_current_user
from app.services.auth.email import (
    send_password_reset_email,
    send_verification_email,
)
from app.services.auth.exceptions import (
    AccountLockedError,
    OAuthError,
    RefreshTokenReuseError,
    TokenExpiredError,
    TokenInvalidError,
    WeakPasswordError,
)
from app.services.auth.oauth import (
    exchange_github_code,
    exchange_google_code,
    fetch_github_profile_with_access_token,
    fetch_google_profile_with_access_token,
    verify_google_id_token,
)
from app.services.auth.password import (
    check_strength,
    hash_password,
    verify_password,
)
from app.services.auth.tokens import (
    create_access_token,
    create_purpose_token,
    create_refresh_token,
    decode_access_token,
    find_refresh_token,
    make_device_fingerprint,
    revoke_all_user_tokens,
    revoke_token,
    rotate_refresh_token,
)
from app.services.auth.totp import (
    RECOVERY_CODE_COUNT,
    begin_enrollment,
    consume_recovery_code,
    generate_recovery_codes,
    hash_recovery_codes,
    verify_totp_code,
)

log = structlog.get_logger("auth.router")

router = APIRouter(prefix="/api/auth", tags=["auth"])

REGISTRATION_GRANT_CREDITS = registration_grant_credits()
REFRESH_COOKIE_NAME = "sr_refresh"


# ---------------------------------------------------------------------------
# Pydantic request/response schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=10, max_length=200)
    display_name: str = Field("", max_length=200)
    accepted_tos_version: str = Field(..., min_length=1, max_length=32)
    marketing_opt_in: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)


class CallbackRequest(BaseModel):
    provider: Literal["google", "github"]
    code: str | None = Field(None, min_length=1, max_length=4096)
    id_token: str | None = Field(None, min_length=1, max_length=8192)
    access_token: str | None = Field(None, min_length=1, max_length=4096)
    redirect_uri: str = Field(default="http://localhost:3000", max_length=1024)

    @model_validator(mode="after")
    def require_one_credential(self) -> "CallbackRequest":
        if not any([self.code, self.id_token, self.access_token]):
            raise ValueError("One of code, id_token, or access_token is required")
        return self


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=4096)
    new_password: str = Field(..., min_length=10, max_length=200)


class EnrollTfaResponse(BaseModel):
    secret: str
    provisioning_uri: str


class VerifyTfaRequest(BaseModel):
    code: str | None = Field(None, min_length=6, max_length=6)
    recovery_code: str | None = Field(None, max_length=24)
    # When verifying the *enrollment* step the user is already
    # authenticated; when completing the 2FA-on-login flow the caller
    # passes the short-lived 2fa_challenge token they just received.
    challenge_token: str | None = Field(None, max_length=4096)


class DisableTfaRequest(BaseModel):
    code: str | None = Field(None, min_length=6, max_length=6)
    recovery_code: str | None = Field(None, max_length=24)


class MeResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    tier: UserTier
    credit_balance: int
    auth_provider: AuthProvider
    email_verified_at: datetime | None
    has_totp: bool
    closure_requested_at: datetime | None
    suspended_at: datetime | None
    onboarding_completed_at: datetime | None
    onboarding_ai_choice: str | None


class OnboardingPatchRequest(BaseModel):
    ai_choice: Literal["platform"] | None = None
    complete: bool = False


class SessionInfo(BaseModel):
    id: uuid.UUID
    issued_at: datetime
    expires_at: datetime
    device_fingerprint: str
    current: bool


class AuthSuccessResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: MeResponse


class TfaRequiredResponse(BaseModel):
    code: Literal["2fa_required"] = "2fa_required"
    challenge_token: str
    expires_in: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")


def _fingerprint(request: Request) -> str:
    return make_device_fingerprint(_user_agent(request), _client_ip(request))


async def _set_refresh_cookie(response: Response, token: str, expires_in: int) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=expires_in,
        httponly=True,
        secure=is_production_grade(),  # local dev http://localhost has no TLS
        samesite="lax",
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/auth",
        httponly=True,
        secure=is_production_grade(),
        samesite="lax",
    )


def _me(user: User, *, credit_balance: int | None = None) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        tier=user.tier,
        credit_balance=credit_balance if credit_balance is not None else user.credit_balance,
        auth_provider=user.auth_provider,
        email_verified_at=user.email_verified_at,
        has_totp=user.has_totp,
        closure_requested_at=user.closure_requested_at,
        suspended_at=user.suspended_at,
        onboarding_completed_at=user.onboarding_completed_at,
        onboarding_ai_choice=user.onboarding_ai_choice,
    )


async def _me_from_ledger(db: AsyncSession, user: User) -> MeResponse:
    """Return profile fields with the authoritative free-credit ledger balance."""
    balance = await get_balance(db, user_id=user.id, credit_kind=CreditKind.free)
    if user.credit_balance != balance:
        user.credit_balance = max(0, balance)
        await db.flush()
    return _me(user, credit_balance=balance)


async def _issue_session(
    db: AsyncSession,
    response: Response,
    *,
    user: User,
    device_fp: str,
) -> AuthSuccessResponse:
    """Mint access + refresh tokens and bind the refresh token in Redis."""
    access = create_access_token(user.id, ttl=settings.ACCESS_TOKEN_TTL_SECONDS)
    issued = await create_refresh_token(
        db,
        user_id=user.id,
        device_fingerprint=device_fp,
        ttl_seconds=settings.REFRESH_TOKEN_TTL_SECONDS,
    )
    await redis_session.bind_refresh_token_to_redis(
        issued.token_id,
        user.id,
        device_fp,
        ttl=settings.REFRESH_TOKEN_TTL_SECONDS,
    )
    await _set_refresh_cookie(response, issued.token, settings.REFRESH_TOKEN_TTL_SECONDS)
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    return AuthSuccessResponse(
        access_token=access,
        expires_in=settings.ACCESS_TOKEN_TTL_SECONDS,
        user=await _me_from_ledger(db, user),
    )


async def _process_failed_login(
    db: AsyncSession,
    request: Request,
    *,
    user: User | None,
    reason: str,
) -> None:
    """Write the failure row + flip on lockout if threshold reached.

    Always commits before returning/raising so audit rows survive the
    HTTPException-driven rollback that the surrounding handler will
    trigger.  Without this, every login_failure would be lost.
    """
    await record_auth_event(
        db,
        user_id=user.id if user else None,
        event=AuthAuditEvent.login_failure,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"reason": reason},
    )
    if user is None:
        await db.commit()
        return
    locked = await is_account_locked(db, user_id=user.id)
    if locked:
        await record_auth_event(
            db,
            user_id=user.id,
            event=AuthAuditEvent.suspicious_login,
            ip=_client_ip(request),
            user_agent=_user_agent(request),
            metadata={"reason": "lockout_threshold_reached"},
        )
        await record_auth_event(
            db,
            user_id=user.id,
            event=AuthAuditEvent.account_locked,
            ip=_client_ip(request),
            user_agent=_user_agent(request),
            metadata={},
        )
        await db.commit()
        raise AccountLockedError("account temporarily locked after repeated failures")
    await db.commit()


def _attach_closure_header(request: Request, response: Response) -> None:
    pending = getattr(request.state, "closure_pending_at", None)
    if pending:
        response.headers[CLOSURE_HEADER] = pending


# ===========================================================================
# Routes
# ===========================================================================


# 1. POST /register --------------------------------------------------------
@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    response: Response,
    payload: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthSuccessResponse:
    email = payload.email.lower().strip()

    # Reject weak passwords up-front using zxcvbn (§18.2).
    try:
        check_strength(payload.password, user_inputs=[email, payload.display_name or ""])
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "weak_password",
                "score": exc.score,
                "suggestions": exc.suggestions,
            },
        ) from exc

    existing = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        if existing.auth_provider != AuthProvider.email and not existing.password_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "email_registered_with_sso",
                    "provider": existing.auth_provider.value,
                },
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "email_already_registered"},
        )

    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name=payload.display_name or email.split("@", 1)[0],
        auth_provider=AuthProvider.email,
        password_hash=hash_password(payload.password),
        tier=UserTier.free,
        credit_balance=REGISTRATION_GRANT_CREDITS,
        accepted_tos_version=payload.accepted_tos_version,
        marketing_opt_in=payload.marketing_opt_in,
        last_login_ip=_client_ip(request) or None,
    )
    db.add(user)
    await db.flush()

    # §18.3 — record the registration grant on the credit ledger in
    # the same transaction as the user row.  ``delta`` is the §7.5
    # ledger-extended replacement for the legacy ``amount`` column.
    db.add(
        CreditTransaction(
            id=uuid.uuid4(),
            user_id=user.id,
            delta=REGISTRATION_GRANT_CREDITS,
            action=CreditTransactionAction.registration_grant,
            reason="registration_grant",
            note="initial free credit grant on registration",
        )
    )
    await db.flush()

    # Verification email — fire and forget (logged on failure).
    try:
        await send_verification_email(
            to_email=user.email,
            user_id=user.id,
            display_name=user.display_name,
        )
    except Exception as exc:  # pragma: no cover - email infra side
        log.warning("auth.register.verification_send_failed", error=str(exc))

    await record_auth_event(
        db,
        user_id=user.id,
        event=AuthAuditEvent.login_success,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"reason": "registration"},
    )
    result = await _issue_session(db, response, user=user, device_fp=_fingerprint(request))
    return result


# 2. POST /login -----------------------------------------------------------
@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthSuccessResponse | TfaRequiredResponse:
    email = payload.email.lower().strip()
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if user is None:
        verify_password(payload.password, None)
        try:
            await _process_failed_login(db, request, user=None, reason="unknown_email")
        except AccountLockedError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "account_locked"},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials"},
        )

    if user.auth_provider != AuthProvider.email and not user.password_hash:
        # SSO-only account — no password on file. Guide caller to the provider.
        verify_password(payload.password, None)
        try:
            await _process_failed_login(db, request, user=user, reason="sso_only")
        except AccountLockedError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "account_locked"},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "sso_sign_in_required",
                "provider": user.auth_provider.value,
            },
        )

    if user.is_suspended:
        await record_auth_event(
            db,
            user_id=user.id,
            event=AuthAuditEvent.login_failure,
            ip=_client_ip(request),
            user_agent=_user_agent(request),
            metadata={"reason": "suspended"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "account_suspended"},
        )

    # Pre-check lockout to avoid bcrypt cost on a known-locked account.
    if await is_account_locked(db, user_id=user.id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "account_locked"},
        )

    if not verify_password(payload.password, user.password_hash):
        try:
            await _process_failed_login(db, request, user=user, reason="bad_password")
        except AccountLockedError:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "account_locked"},
            ) from None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials"},
        )

    # Password OK — TOTP gate if enrolled.
    if user.has_totp:
        challenge = create_purpose_token(
            user.id, typ="2fa_challenge", ttl=settings.TFA_CHALLENGE_TTL_SECONDS
        )
        # Don't write login_success yet — wait for the TOTP verify step.
        raise _tfa_required(challenge)

    await record_auth_event(
        db,
        user_id=user.id,
        event=AuthAuditEvent.login_success,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"reason": "password"},
    )
    return await _issue_session(db, response, user=user, device_fp=_fingerprint(request))


def _tfa_required(challenge_token: str) -> HTTPException:
    """Helper that converts the TfaRequired soft-signal into a 401."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=TfaRequiredResponse(
            challenge_token=challenge_token,
            expires_in=settings.TFA_CHALLENGE_TTL_SECONDS,
        ).model_dump(),
    )


# 3. POST /callback (OAuth) ------------------------------------------------
@router.post("/callback")
@limiter.limit("10/minute")
async def oauth_callback(
    request: Request,
    response: Response,
    payload: CallbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthSuccessResponse:
    try:
        if payload.provider == "google":
            if payload.id_token:
                profile = await verify_google_id_token(payload.id_token)
            elif payload.access_token:
                profile = await fetch_google_profile_with_access_token(payload.access_token)
            else:
                profile = await exchange_google_code(
                    payload.code or "",
                    payload.redirect_uri,
                )
        elif payload.id_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "oauth_failed", "message": "GitHub does not support id_token"},
            )
        elif payload.access_token:
            profile = await fetch_github_profile_with_access_token(payload.access_token)
        else:
            profile = await exchange_github_code(
                payload.code or "",
                payload.redirect_uri,
            )
    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "oauth_failed", "message": str(exc)},
        ) from exc

    provider_enum = AuthProvider(payload.provider)

    user = (
        await db.execute(
            select(User).where(
                User.auth_provider == provider_enum,
                User.provider_id == profile["provider_id"],
            )
        )
    ).scalar_one_or_none()
    if user is None:
        # Also reject if the email already belongs to a different provider.
        existing = (
            await db.execute(select(User).where(User.email == profile["email"]))
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "email_already_registered",
                    "with_provider": existing.auth_provider.value,
                },
            )
        user = User(
            id=uuid.uuid4(),
            email=profile["email"],
            display_name=profile["display_name"] or profile["email"].split("@", 1)[0],
            auth_provider=provider_enum,
            provider_id=profile["provider_id"],
            email_verified_at=datetime.now(timezone.utc),  # OAuth provider already verified
            tier=UserTier.free,
            credit_balance=REGISTRATION_GRANT_CREDITS,
            accepted_tos_version="oauth",  # frontend records ToS on the consent step
            last_login_ip=_client_ip(request) or None,
        )
        db.add(user)
        await db.flush()
        db.add(
            CreditTransaction(
                id=uuid.uuid4(),
                user_id=user.id,
                delta=REGISTRATION_GRANT_CREDITS,
                action=CreditTransactionAction.registration_grant,
                reason="registration_grant",
                note=f"registration grant via {provider_enum.value}",
            )
        )
        await db.flush()

    if user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "account_suspended"},
        )

    await record_auth_event(
        db,
        user_id=user.id,
        event=AuthAuditEvent.login_success,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"provider": payload.provider},
    )
    return await _issue_session(db, response, user=user, device_fp=_fingerprint(request))


# 4. POST /logout ----------------------------------------------------------
@router.post("/logout")
@limiter.limit("120/minute")
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> dict[str, Any]:
    if refresh_token:
        row = await find_refresh_token(db, token=refresh_token)
        if row and row.user_id == user.id:
            await revoke_token(db, row=row)
            await redis_session.revoke_redis_token(row.id)
    await record_auth_event(
        db,
        user_id=user.id,
        event=AuthAuditEvent.logout,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"scope": "current"},
    )
    _clear_refresh_cookie(response)
    _attach_closure_header(request, response)
    return {"ok": True}


# 5. POST /logout-all ------------------------------------------------------
@router.post("/logout-all")
@limiter.limit("30/minute")
async def logout_all(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    revoked = await revoke_all_user_tokens(db, user_id=user.id)
    await redis_session.revoke_all_user_tokens(user.id)
    await record_auth_event(
        db,
        user_id=user.id,
        event=AuthAuditEvent.logout,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"scope": "all", "revoked": revoked},
    )
    _clear_refresh_cookie(response)
    _attach_closure_header(request, response)
    return {"ok": True, "revoked": revoked}


# 6. POST /refresh ---------------------------------------------------------
@router.post("/refresh")
@limiter.limit("30/minute")
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> AuthSuccessResponse:
    if not refresh_token:
        raise HTTPException(status_code=401, detail={"code": "missing_refresh_token"})
    device_fp = _fingerprint(request)
    try:
        issued = await rotate_refresh_token(
            db,
            token=refresh_token,
            device_fingerprint=device_fp,
            ttl_seconds=settings.REFRESH_TOKEN_TTL_SECONDS,
        )
    except RefreshTokenReuseError as exc:
        # ``rotate_refresh_token`` already called revoke_all_user_tokens
        # on the DB session; we must commit it before the HTTPException
        # propagates or the get_db rollback will undo the chain kill.
        if exc.user_id:
            try:
                await record_auth_event(
                    db,
                    user_id=uuid.UUID(exc.user_id),
                    event=AuthAuditEvent.suspicious_login,
                    ip=_client_ip(request),
                    user_agent=_user_agent(request),
                    metadata={"reason": "refresh_token_reuse"},
                )
            except Exception:  # pragma: no cover
                pass
            await db.commit()
            await redis_session.revoke_all_user_tokens(exc.user_id)
        else:
            await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "refresh_token_reuse"},
        ) from exc
    except TokenExpiredError:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "refresh_token_expired"},
        ) from None
    except TokenInvalidError:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "refresh_token_invalid"},
        ) from None

    user = (
        await db.execute(select(User).where(User.id == issued.row.user_id))
    ).scalar_one_or_none()
    if user is None or user.is_suspended:
        await revoke_token(db, row=issued.row)
        await redis_session.revoke_redis_token(issued.token_id)
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=403, detail={"code": "account_suspended"})

    await redis_session.bind_refresh_token_to_redis(
        issued.token_id, user.id, device_fp, ttl=settings.REFRESH_TOKEN_TTL_SECONDS
    )
    await _set_refresh_cookie(response, issued.token, settings.REFRESH_TOKEN_TTL_SECONDS)
    access = create_access_token(user.id, ttl=settings.ACCESS_TOKEN_TTL_SECONDS)
    return AuthSuccessResponse(
        access_token=access,
        expires_in=settings.ACCESS_TOKEN_TTL_SECONDS,
        user=await _me_from_ledger(db, user),
    )


# 7. GET /me ---------------------------------------------------------------
@router.get("/me")
@limiter.limit("120/minute")
async def me(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> MeResponse:
    _attach_closure_header(request, response)
    return await _me_from_ledger(db, user)


# 7b. PATCH /onboarding ----------------------------------------------------
@router.patch("/onboarding")
@limiter.limit("30/minute")
async def patch_onboarding(
    request: Request,
    body: OnboardingPatchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> MeResponse:
    if body.ai_choice is not None:
        user.onboarding_ai_choice = body.ai_choice

    if body.complete:
        choice = body.ai_choice or user.onboarding_ai_choice
        if choice != "platform":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "ai_choice_required"},
            )
        user.onboarding_ai_choice = "platform"
        user.onboarding_completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(user)
    return await _me_from_ledger(db, user)


# 8. GET /sessions ---------------------------------------------------------
@router.get("/sessions")
@limiter.limit("120/minute")
async def list_sessions(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> list[SessionInfo]:
    current_id: uuid.UUID | None = None
    if refresh_token:
        current_row = await find_refresh_token(db, token=refresh_token)
        if current_row and current_row.user_id == user.id:
            current_id = current_row.id

    rows = (
        await db.execute(
            select(RefreshToken)
            .where(RefreshToken.user_id == user.id)
            .where(RefreshToken.revoked_at.is_(None))
            .order_by(RefreshToken.issued_at.desc())
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    _attach_closure_header(request, response)
    return [
        SessionInfo(
            id=row.id,
            issued_at=row.issued_at,
            expires_at=row.expires_at,
            device_fingerprint=row.device_fingerprint,
            current=(row.id == current_id),
        )
        for row in rows
        if row.expires_at > now
    ]


# 9. DELETE /sessions/{id} -------------------------------------------------
@router.delete("/sessions/{session_id}")
@limiter.limit("120/minute")
async def revoke_session(
    request: Request,
    response: Response,
    session_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    row = (
        await db.execute(
            select(RefreshToken).where(
                RefreshToken.id == session_id,
                RefreshToken.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "session_not_found"})
    await revoke_token(db, row=row)
    await redis_session.revoke_redis_token(row.id)
    _attach_closure_header(request, response)
    return {"ok": True}


# 10. POST /verify/send ----------------------------------------------------
@router.post("/verify/send")
@limiter.limit("1/5minute")
async def verify_send(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    if user.is_email_verified:
        _attach_closure_header(request, response)
        return {"ok": True, "already_verified": True}
    try:
        await send_verification_email(
            to_email=user.email,
            user_id=user.id,
            display_name=user.display_name,
        )
    except Exception as exc:  # pragma: no cover
        log.warning("auth.verify.send_failed", error=str(exc))
        raise HTTPException(status_code=502, detail={"code": "email_send_failed"})
    _attach_closure_header(request, response)
    return {"ok": True}


# 11. GET /verify/{token} --------------------------------------------------
@router.get("/verify/{token}")
async def verify_confirm(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        claims = decode_access_token(token, expected_type="verify")
    except TokenExpiredError:
        raise HTTPException(status_code=400, detail={"code": "verify_token_expired"})
    except TokenInvalidError:
        raise HTTPException(status_code=400, detail={"code": "verify_token_invalid"})

    user_id = uuid.UUID(claims["sub"])
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail={"code": "user_not_found"})
    if not user.is_email_verified:
        user.email_verified_at = datetime.now(timezone.utc)
        await db.flush()
    return {"ok": True, "email": user.email, "verified_at": user.email_verified_at}


# 12. POST /password/forgot ------------------------------------------------
@router.post("/password/forgot")
@limiter.limit("3/minute")
async def password_forgot(
    request: Request,
    payload: ForgotPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    email = payload.email.lower().strip()
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    # Idempotent: always pretend it worked so we never reveal which
    # emails are registered.
    if user is not None and user.auth_provider == AuthProvider.email:
        try:
            await send_password_reset_email(
                to_email=user.email,
                user_id=user.id,
                display_name=user.display_name,
            )
        except Exception as exc:  # pragma: no cover
            log.warning("auth.password_forgot.send_failed", error=str(exc))
    return {"ok": True}


# 13. POST /password/reset -------------------------------------------------
@router.post("/password/reset")
@limiter.limit("10/minute")
async def password_reset(
    request: Request,
    response: Response,
    payload: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        claims = decode_access_token(payload.token, expected_type="reset")
    except TokenExpiredError:
        raise HTTPException(status_code=400, detail={"code": "reset_token_expired"})
    except TokenInvalidError:
        raise HTTPException(status_code=400, detail={"code": "reset_token_invalid"})

    user_id = uuid.UUID(claims["sub"])
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or user.auth_provider != AuthProvider.email:
        raise HTTPException(status_code=404, detail={"code": "user_not_found"})

    try:
        check_strength(payload.new_password, user_inputs=[user.email, user.display_name])
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "weak_password",
                "score": exc.score,
                "suggestions": exc.suggestions,
            },
        ) from exc

    user.password_hash = hash_password(payload.new_password)
    await db.flush()

    # §18.2 requirement: reset invalidates ALL refresh tokens.
    await revoke_all_user_tokens(db, user_id=user.id)
    await redis_session.revoke_all_user_tokens(user.id)

    await record_auth_event(
        db,
        user_id=user.id,
        event=AuthAuditEvent.password_reset,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={},
    )
    _clear_refresh_cookie(response)
    return {"ok": True}


# 14. POST /2fa/enroll -----------------------------------------------------
@router.post("/2fa/enroll")
@limiter.limit("10/minute")
async def tfa_enroll(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> EnrollTfaResponse:
    # Allow re-enroll while enrollment is still pending.  Once fully
    # enrolled, the user must disable first.
    if user.has_totp:
        raise HTTPException(status_code=400, detail={"code": "tfa_already_enrolled"})
    enrollment = begin_enrollment(account_label=user.email)
    user.totp_secret = enrollment.encrypted_secret
    user.totp_recovery_codes = []  # codes only minted after confirm
    await db.flush()
    _attach_closure_header(request, response)
    return EnrollTfaResponse(
        secret=enrollment.secret_b32,
        provisioning_uri=enrollment.provisioning_uri,
    )


# 15. POST /2fa/verify -----------------------------------------------------
@router.post("/2fa/verify")
@limiter.limit("10/minute")
async def tfa_verify(
    request: Request,
    response: Response,
    payload: VerifyTfaRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthSuccessResponse | dict[str, Any]:
    """Dual-purpose endpoint:

    - If ``challenge_token`` is supplied, verify it and complete login
      (caller is not yet authenticated).
    - Otherwise the caller must present a bearer access token and is
      finishing enrollment — emit recovery codes and persist them.
    """
    if payload.challenge_token:
        return await _tfa_verify_login(request, response, payload, db)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "auth_required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    raw_token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_access_token(raw_token, expected_type="access")
    except (TokenExpiredError, TokenInvalidError):
        raise HTTPException(status_code=401, detail={"code": "invalid_access_token"})
    user = (
        await db.execute(select(User).where(User.id == uuid.UUID(claims["sub"])))
    ).scalar_one_or_none()
    if user is None or user.is_suspended:
        raise HTTPException(status_code=401, detail={"code": "auth_required"})
    return await _tfa_verify_enrollment(request, response, payload, db, user)


async def _tfa_verify_login(
    request: Request,
    response: Response,
    payload: VerifyTfaRequest,
    db: AsyncSession,
) -> AuthSuccessResponse:
    try:
        claims = decode_access_token(
            payload.challenge_token,  # type: ignore[arg-type]
            expected_type="2fa_challenge",
        )
    except (TokenExpiredError, TokenInvalidError):
        raise HTTPException(
            status_code=401, detail={"code": "challenge_token_invalid"}
        ) from None

    user = (
        await db.execute(select(User).where(User.id == uuid.UUID(claims["sub"])))
    ).scalar_one_or_none()
    if user is None or not user.has_totp or user.is_suspended:
        raise HTTPException(status_code=401, detail={"code": "tfa_invalid"})

    ok = False
    used_recovery = False
    if payload.code:
        ok = verify_totp_code(user.totp_secret or b"", payload.code)
    if not ok and payload.recovery_code:
        ok, remaining = consume_recovery_code(
            list(user.totp_recovery_codes), code=payload.recovery_code
        )
        if ok:
            user.totp_recovery_codes = remaining
            used_recovery = True
            await db.flush()

    if not ok:
        await record_auth_event(
            db,
            user_id=user.id,
            event=AuthAuditEvent.login_failure,
            ip=_client_ip(request),
            user_agent=_user_agent(request),
            metadata={"reason": "tfa_invalid"},
        )
        raise HTTPException(status_code=401, detail={"code": "tfa_invalid"})

    await record_auth_event(
        db,
        user_id=user.id,
        event=AuthAuditEvent.login_success,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"reason": "tfa_recovery" if used_recovery else "tfa"},
    )
    return await _issue_session(db, response, user=user, device_fp=_fingerprint(request))


async def _tfa_verify_enrollment(
    request: Request,
    response: Response,
    payload: VerifyTfaRequest,
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    if user.totp_secret is None:
        raise HTTPException(status_code=400, detail={"code": "tfa_not_started"})
    if not payload.code:
        raise HTTPException(status_code=400, detail={"code": "tfa_code_required"})
    if not verify_totp_code(user.totp_secret, payload.code):
        raise HTTPException(status_code=400, detail={"code": "tfa_invalid"})

    plaintext_codes = generate_recovery_codes(RECOVERY_CODE_COUNT)
    user.totp_recovery_codes = hash_recovery_codes(plaintext_codes)
    await db.flush()

    await record_auth_event(
        db,
        user_id=user.id,
        event=AuthAuditEvent.tfa_enroll,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"recovery_code_count": RECOVERY_CODE_COUNT},
    )
    _attach_closure_header(request, response)
    return {
        "ok": True,
        "recovery_codes": plaintext_codes,  # shown exactly once
    }


# 16. POST /2fa/disable ----------------------------------------------------
@router.post("/2fa/disable")
@limiter.limit("10/minute")
async def tfa_disable(
    request: Request,
    response: Response,
    payload: DisableTfaRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    if not user.has_totp:
        raise HTTPException(status_code=400, detail={"code": "tfa_not_enrolled"})

    ok = False
    if payload.code and verify_totp_code(user.totp_secret or b"", payload.code):
        ok = True
    elif payload.recovery_code:
        matched, _ = consume_recovery_code(
            list(user.totp_recovery_codes), code=payload.recovery_code
        )
        ok = matched
    if not ok:
        raise HTTPException(status_code=401, detail={"code": "tfa_invalid"})

    user.totp_secret = None
    user.totp_recovery_codes = []
    await db.flush()

    await record_auth_event(
        db,
        user_id=user.id,
        event=AuthAuditEvent.tfa_disable,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={},
    )
    _attach_closure_header(request, response)
    return {"ok": True}


__all__ = ["REFRESH_COOKIE_NAME", "router"]
