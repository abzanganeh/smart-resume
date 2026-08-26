"""Session capability binding for the anonymous tailoring flow (OWASP A01).

Once a session is claimed (``session.user_id`` set), a different user's bearer
token must receive HTTP 403 — not silently re-bind or overwrite ownership.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.auth import session as redis_session
from app.services.auth.tokens import TokenExpiredError, TokenInvalidError, decode_access_token
from app.services.session_store import update_session


def _session_replaced() -> HTTPException:
    """Same 401 shape ``get_current_user`` returns, so clients re-auth alike."""
    return HTTPException(status_code=401, detail={"code": "session_replaced"})


async def _auth_session_is_current(claims: dict, subject: str) -> bool:
    """Whether the token's ``sid`` still names the user's active login.

    ``get_current_user`` applies this rule to every gated route, so a token
    superseded by a newer login is already dead everywhere else.  The helpers
    below decode the same access token without that dependency, so omitting
    the check would leave a revoked token able to drive a claimed tailoring
    session — spending the owner's credits and reaching their corpus.
    """
    sid = claims.get("sid")
    if not sid:
        return True
    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        return False
    active_sid = await redis_session.get_active_auth_session_id(user_id)
    return not active_sid or str(sid) == active_sid


async def resolve_bearer_user_id(
    authorization: str | None,
    session,
) -> str | None:
    """Resolve the effective user id for a session-scoped route.

    - No bearer header → return the session's existing ``user_id`` (may be None).
    - Valid bearer → claim the session on first use, or verify the bearer matches
      an already-claimed session (403 on mismatch).
    - Invalid/expired bearer → fall back to ``session.user_id`` so anonymous
      routes keep working; authenticated-only routes must enforce separately.
    - Superseded bearer → 401, matching ``get_current_user``.  Falling back
      here would hand the caller the claimed session's owner id, which is
      exactly the access the newer login was meant to revoke.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return session.user_id
    token = authorization[7:].strip()
    if not token:
        return session.user_id
    try:
        claims = decode_access_token(token, expected_type="access")
        bearer_sub = str(claims.get("sub") or "")
        if not bearer_sub:
            return session.user_id
        if not await _auth_session_is_current(claims, bearer_sub):
            raise _session_replaced()
        if session.user_id and session.user_id != bearer_sub:
            raise HTTPException(
                status_code=403,
                detail="Session does not belong to this user.",
            )
        if session.user_id != bearer_sub:
            session.user_id = bearer_sub
            await update_session(session)
        return bearer_sub
    except (TokenExpiredError, TokenInvalidError):
        return session.user_id


async def bind_session_user_from_bearer(
    authorization: str | None,
    session,
) -> None:
    """Best-effort bind on session creation; ignores invalid bearer tokens.

    A superseded token leaves the new session anonymous rather than raising:
    the route is public, so refusing to bind is enough to keep a revoked
    login from attaching work to the account.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return
    token = authorization[7:].strip()
    if not token:
        return
    try:
        claims = decode_access_token(token, expected_type="access")
        sub = str(claims.get("sub") or "")
        if sub and await _auth_session_is_current(claims, sub):
            session.user_id = sub
            await update_session(session)
    except (TokenExpiredError, TokenInvalidError):
        pass


def bearer_claims_or_none(authorization: str | None) -> dict | None:
    """Return decoded access-token claims when a valid bearer is present."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    try:
        return decode_access_token(token, expected_type="access")
    except (TokenExpiredError, TokenInvalidError):
        return None


async def require_session_user(
    authorization: str | None,
    session,
    db: AsyncSession,
) -> User:
    """Require a valid bearer that matches a claimed session; load the User row."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        claims = decode_access_token(token, expected_type="access")
        bearer_sub = str(claims.get("sub") or "")
        if not bearer_sub:
            raise HTTPException(status_code=401, detail="Invalid access token")
        if not await _auth_session_is_current(claims, bearer_sub):
            raise _session_replaced()
        if session.user_id and session.user_id != bearer_sub:
            raise HTTPException(
                status_code=403,
                detail="Session does not belong to this user.",
            )
        if session.user_id != bearer_sub:
            session.user_id = bearer_sub
            await update_session(session)
        try:
            uid = uuid.UUID(bearer_sub)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid access token") from None
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except (TokenExpiredError, TokenInvalidError):
        raise HTTPException(status_code=401, detail="Invalid access token") from None


__all__ = [
    "bind_session_user_from_bearer",
    "bearer_claims_or_none",
    "require_session_user",
    "resolve_bearer_user_id",
]
