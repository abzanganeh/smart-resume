"""Extension-friendly auth routes (Strategy B Phase 2).

The browser extension cannot use HttpOnly cookies (service workers do not
have access to cookies), so these endpoints return the refresh token in the
JSON response body. Everything else — lockout, audit, rotation — is identical
to the web auth flow.

Guarded by ``EXTENSION_AUTH_ENABLED`` feature flag so it can be disabled
in production before the extension is publicly released.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_db
from app.limiter import limiter
from app.models.user import AuthAuditEvent, AuthProvider, User
from app.routers.auth import MeResponse, _me
from app.services.auth import session as redis_session
from app.services.auth.audit import is_account_locked, record_auth_event
from app.services.auth.exceptions import (
    RefreshTokenReuseError,
    TokenExpiredError,
    TokenInvalidError,
)
from app.services.auth.password import verify_password
from app.services.auth.tokens import (
    create_access_token,
    create_refresh_token,
    make_device_fingerprint,
    rotate_refresh_token,
)

log = structlog.get_logger("auth.extension")

router = APIRouter(prefix="/api/auth/extension", tags=["auth-extension"])


class ExtensionLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)


class ExtensionRefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1, max_length=512)


class ExtensionAuthResponse(BaseModel):
    """Access + refresh tokens returned in the JSON body (no cookie)."""

    access_token: str
    refresh_token: str
    expires_in: int
    user: MeResponse


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")


def _fingerprint(request: Request) -> str:
    return make_device_fingerprint(_user_agent(request), _client_ip(request))


def _require_enabled() -> None:
    if not settings.EXTENSION_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "extension_auth_disabled"},
        )


async def _issue_extension_session(
    db: AsyncSession,
    request: Request,
    user: User,
) -> ExtensionAuthResponse:
    access = create_access_token(user.id, ttl=settings.ACCESS_TOKEN_TTL_SECONDS)
    device_fp = _fingerprint(request)
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
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    return ExtensionAuthResponse(
        access_token=access,
        refresh_token=issued.token,
        expires_in=settings.ACCESS_TOKEN_TTL_SECONDS,
        user=_me(user),
    )


@router.post("/login", response_model=ExtensionAuthResponse)
@limiter.limit("10/minute")
async def extension_login(
    request: Request,
    payload: ExtensionLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExtensionAuthResponse:
    """Authenticate and return tokens in the response body.

    Identical lockout and audit semantics to ``POST /api/auth/login``.
    Refresh token is in the JSON body so service workers can store it
    in ``chrome.storage.local``.
    """
    _require_enabled()

    email = payload.email.lower().strip()
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if user is None or user.auth_provider != AuthProvider.email:
        verify_password(payload.password, None)
        await record_auth_event(
            db,
            user_id=None,
            event=AuthAuditEvent.login_failure,
            ip=_client_ip(request),
            user_agent=_user_agent(request),
            metadata={"reason": "unknown_email", "source": "extension"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials"},
        )

    if user.is_suspended:
        await record_auth_event(
            db,
            user_id=user.id,
            event=AuthAuditEvent.login_failure,
            ip=_client_ip(request),
            user_agent=_user_agent(request),
            metadata={"reason": "suspended", "source": "extension"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "account_suspended"},
        )

    if await is_account_locked(db, user_id=user.id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "account_locked"},
        )

    if not verify_password(payload.password, user.password_hash):
        await record_auth_event(
            db,
            user_id=user.id,
            event=AuthAuditEvent.login_failure,
            ip=_client_ip(request),
            user_agent=_user_agent(request),
            metadata={"reason": "bad_password", "source": "extension"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials"},
        )

    await record_auth_event(
        db,
        user_id=user.id,
        event=AuthAuditEvent.login_success,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"reason": "password", "source": "extension"},
    )
    return await _issue_extension_session(db, request, user)


@router.post("/refresh", response_model=ExtensionAuthResponse)
@limiter.limit("30/minute")
async def extension_refresh(
    request: Request,
    payload: ExtensionRefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExtensionAuthResponse:
    """Rotate a refresh token. Body-based, no cookies.

    Rotation semantics are identical to ``POST /api/auth/refresh``:
    the old token is revoked, a new access + refresh pair is issued.
    """
    _require_enabled()

    device_fp = _fingerprint(request)
    try:
        issued = await rotate_refresh_token(
            db,
            token=payload.refresh_token,
            device_fingerprint=device_fp,
            ttl_seconds=settings.REFRESH_TOKEN_TTL_SECONDS,
        )
    except RefreshTokenReuseError as exc:
        if exc.user_id:
            try:
                await record_auth_event(
                    db,
                    user_id=uuid.UUID(exc.user_id),
                    event=AuthAuditEvent.suspicious_login,
                    ip=_client_ip(request),
                    user_agent=_user_agent(request),
                    metadata={"reason": "refresh_token_reuse", "source": "extension"},
                )
            except Exception:  # pragma: no cover
                pass
            await db.commit()
            await redis_session.revoke_all_user_tokens(exc.user_id)
        else:
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "refresh_token_reuse"},
        ) from exc
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "refresh_token_expired"},
        ) from None
    except TokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "refresh_token_invalid"},
        ) from None

    user = (
        await db.execute(select(User).where(User.id == issued.row.user_id))
    ).scalar_one_or_none()
    if user is None or user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "account_suspended"},
        )

    await redis_session.bind_refresh_token_to_redis(
        issued.token_id,
        user.id,
        device_fp,
        ttl=settings.REFRESH_TOKEN_TTL_SECONDS,
    )
    access = create_access_token(user.id, ttl=settings.ACCESS_TOKEN_TTL_SECONDS)
    return ExtensionAuthResponse(
        access_token=access,
        refresh_token=issued.token,
        expires_in=settings.ACCESS_TOKEN_TTL_SECONDS,
        user=_me(user),
    )
