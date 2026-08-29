"""FastAPI dependencies for the auth surface.

- ``get_current_user``: verifies the access JWT in ``Authorization:
  Bearer …``, loads the user, refuses suspended accounts (403), and
  attaches an ``X-Account-Closure-Pending`` header when the account
  has a closure request in-flight (§19.6).

- ``get_current_user_id``: lightweight variant for handlers that only
  need the user id (and not the full row).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.models.user import User
from app.services.auth.exceptions import (
    TokenExpiredError,
    TokenInvalidError,
)
from app.services.auth import session as redis_session
from app.services.auth.tokens import decode_access_token

CLOSURE_HEADER = "X-Account-Closure-Pending"

EMAIL_VERIFICATION_REQUIRED_DETAIL = {
    "code": "email_verification_required",
    "message": "Verify your email before using AI features.",
}


async def assert_user_email_verified(
    db: AsyncSession,
    user_id: str | uuid.UUID,
) -> None:
    """Raise 403 when an authenticated user has not confirmed their email."""
    try:
        uid = uuid.UUID(str(user_id))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=EMAIL_VERIFICATION_REQUIRED_DETAIL,
        ) from None
    user = (
        await db.execute(select(User).where(User.id == uid))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=EMAIL_VERIFICATION_REQUIRED_DETAIL,
        )


_bearer = HTTPBearer(auto_error=False, scheme_name="JWT")


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,  # type: ignore[assignment]
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = decode_access_token(credentials.credentials, expected_type="access")
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token expired",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from None
    except TokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from None

    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Token missing subject") from exc

    sid = claims.get("sid")
    if sid:
        active_sid = await redis_session.get_active_auth_session_id(user_id)
        if active_sid and sid != active_sid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "session_replaced"},
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )

    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    if user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "account_suspended",
                "suspended_at": user.suspended_at.isoformat() if user.suspended_at else None,
                "reason": user.suspension_reason,
            },
        )

    if user.is_closure_pending:
        # Warn but do not block — closure has a 30-day grace window per §19.6.
        request.state.closure_pending_at = (
            user.closure_requested_at.isoformat() if user.closure_requested_at else None
        )

    return user


async def get_current_user_id(
    user: Annotated[User, Depends(get_current_user)],
) -> uuid.UUID:
    return user.id


async def require_verified_email(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Reject authenticated users who have not confirmed their email address."""
    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=EMAIL_VERIFICATION_REQUIRED_DETAIL,
        )
    return user


VerifiedUser = Annotated[User, Depends(require_verified_email)]


__all__ = [
    "CLOSURE_HEADER",
    "EMAIL_VERIFICATION_REQUIRED_DETAIL",
    "VerifiedUser",
    "assert_user_email_verified",
    "get_current_user",
    "get_current_user_id",
    "require_verified_email",
]
