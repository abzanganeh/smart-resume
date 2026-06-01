"""Admin auth dependencies + default-deny RBAC gate (Step 35 / IMPLEMENTATION_PLAN section 8.4.1).

Two public helpers:

- :func:`get_current_admin`        - decode a session token and load the admin row.
- :func:`require_admin_role(*roles)` - returns a FastAPI ``Depends`` that
  asserts the admin's role is in the allowlist.  Marker-aware: every
  Dependency object created here carries an ``__admin_role_dep__`` flag
  so the default-deny middleware can detect it on the route.

Default-deny enforcement (section 8.4.1):

- The middleware in :class:`AdminDefaultDenyMiddleware` walks the matched
  route's full dependency tree and short-circuits with HTTP 403
  ``{"code": "missing_rbac_gate"}`` when no ``require_admin_role`` is
  found AND the route is not explicitly marked ``admin_public_route``.

The marker pattern (rather than examining route paths) makes the
behaviour testable in isolation: ``test_rbac_coverage.py`` introspects
the same marker.
"""

from __future__ import annotations

from typing import Annotated, Callable, Iterable

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match
from starlette.types import ASGIApp

from app.db.engine import get_db
from app.models.admin import AdminRole, AdminUser
from app.services.admin_auth.tokens import (
    AdminSessionBindingMismatch,
    AdminSessionClaims,
    AdminSessionIdle,
    AdminSessionNotFound,
    AdminTokenExpired,
    AdminTokenInvalid,
    decode_admin_session_token,
    make_ua_fingerprint,
)

log = structlog.get_logger("admin.auth_deps")

_admin_bearer = HTTPBearer(auto_error=False, scheme_name="AdminJWT")

# Sentinel attribute names used by ``test_rbac_coverage.py``.
RBAC_DEP_MARKER = "__admin_role_dep__"
ADMIN_PUBLIC_MARKER = "__admin_public__"


# ---------------------------------------------------------------------------
# Request-context helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str:
    """Best-effort client IP for session binding.

    Honours ``X-Forwarded-For`` first hop when present (set by the
    reverse proxy) and falls back to ``request.client.host``.
    """
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else ""


def _request_ua_fingerprint(request: Request) -> str:
    return make_ua_fingerprint(
        request.headers.get("user-agent", ""),
        request.headers.get("accept-language", ""),
    )


# ---------------------------------------------------------------------------
# get_current_admin
# ---------------------------------------------------------------------------


async def get_current_admin(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_admin_bearer)
    ] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,  # type: ignore[assignment]
) -> AdminUser:
    """Resolve and verify the current admin from an ``Authorization: Bearer`` header.

    Order of checks:

    1. Bearer header present.
    2. JWT signature, ``typ=admin_session``.
    3. Redis session record present.
    4. Bound IP matches request IP.
    5. Bound UA fingerprint matches request UA.
    6. Idle window not elapsed.
    7. AdminUser row exists and is not suspended.

    Each failure surfaces as HTTP 401 except suspension which is 403.
    The matched ``AdminUser`` and the verified claims are stashed onto
    ``request.state`` so downstream layers can read them without
    re-parsing the token.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "admin_unauthenticated"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    request_ip = _client_ip(request)
    request_ua = _request_ua_fingerprint(request)
    try:
        claims: AdminSessionClaims = await decode_admin_session_token(
            credentials.credentials,
            request_ip=request_ip,
            request_ua_fingerprint=request_ua,
        )
    except AdminTokenExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "admin_session_expired"},
        ) from exc
    except AdminTokenInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "admin_token_invalid"},
        ) from exc
    except AdminSessionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "admin_session_revoked"},
        ) from exc
    except AdminSessionBindingMismatch as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "admin_session_binding_mismatch"},
        ) from exc
    except AdminSessionIdle as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "admin_session_idle"},
        ) from exc

    admin = (
        await db.execute(select(AdminUser).where(AdminUser.id == claims.admin_id))
    ).scalar_one_or_none()
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "admin_not_found"},
        )
    if admin.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "admin_suspended"},
        )
    if admin.must_change_password or admin.must_enroll_2fa:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "admin_setup_incomplete",
                "must_change_password": admin.must_change_password,
                "must_enroll_2fa": admin.must_enroll_2fa,
            },
        )
    request.state.admin = admin
    request.state.admin_session_claims = claims
    return admin


# ---------------------------------------------------------------------------
# require_admin_role(*roles)
# ---------------------------------------------------------------------------


def _normalize_role(role: str | AdminRole) -> AdminRole:
    if isinstance(role, AdminRole):
        return role
    return AdminRole(role)


def require_admin_role(*roles: str | AdminRole) -> Callable[..., AdminUser]:
    """Return a FastAPI dependency that asserts ``admin.role`` is in ``roles``.

    The returned function carries an ``__admin_role_dep__`` attribute
    set to the frozenset of allowed role values.  The default-deny
    middleware and ``test_rbac_coverage.py`` look for this marker on
    the dependant tree of every admin route.

    Empty ``roles`` is illegal: handlers must specify at least one role.
    """
    if not roles:
        raise ValueError("require_admin_role(): at least one role is required")
    allowed: frozenset[AdminRole] = frozenset(_normalize_role(r) for r in roles)

    async def _dep(
        admin: Annotated[AdminUser, Depends(get_current_admin)],
    ) -> AdminUser:
        if admin.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "admin_role_forbidden",
                    "required_roles": sorted(r.value for r in allowed),
                    "actor_role": admin.role.value,
                },
            )
        return admin

    setattr(_dep, RBAC_DEP_MARKER, frozenset(r.value for r in allowed))
    _dep.__doc__ = (
        f"Require admin role in {{{', '.join(sorted(r.value for r in allowed))}}}."
    )
    return _dep


# ---------------------------------------------------------------------------
# admin_public_route(): explicit opt-out marker for /api/admin/auth/*
# ---------------------------------------------------------------------------


def admin_public_route(endpoint: Callable) -> Callable:
    """Mark an admin route as intentionally public (login / accept-invite).

    The default-deny middleware will permit the request through, and
    ``test_rbac_coverage.py`` will accept the route as legitimately
    ungated.
    """
    setattr(endpoint, ADMIN_PUBLIC_MARKER, True)
    return endpoint


# ---------------------------------------------------------------------------
# Default-deny middleware
# ---------------------------------------------------------------------------


def _route_has_rbac_dep(route: APIRoute) -> bool:
    """Walk the dependant tree and look for the ``__admin_role_dep__`` marker."""
    dep = route.dependant
    stack = list(dep.dependencies)
    while stack:
        sub = stack.pop()
        if sub.call is not None and getattr(sub.call, RBAC_DEP_MARKER, None) is not None:
            return True
        stack.extend(sub.dependencies)
    return False


def _route_is_admin_public(route: APIRoute) -> bool:
    return bool(getattr(route.endpoint, ADMIN_PUBLIC_MARKER, False))


def admin_route_is_gated(route: APIRoute) -> bool:
    """Return ``True`` when the route is either RBAC-gated or marked public.

    Used by ``test_rbac_coverage.py``; importing this helper from the
    test prevents the coverage check from drifting against the
    middleware logic.
    """
    return _route_has_rbac_dep(route) or _route_is_admin_public(route)


def iter_admin_routes(app) -> Iterable[APIRoute]:
    """Iterate ``APIRoute`` instances under ``/api/admin``."""
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/admin"):
            yield route


class AdminDefaultDenyMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that returns 403 for ungated /api/admin/* routes.

    The check is performed per-request rather than at startup so that
    routes added after app build (test fixtures, etc.) are still
    covered.  The middleware is a no-op for non-admin paths.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path or ""
        # Allow CORS preflight to pass through unchanged - the CORS
        # middleware sits closer to the wire and already answers it.
        if request.method == "OPTIONS":
            return await call_next(request)
        if not path.startswith("/api/admin"):
            return await call_next(request)

        scope = request.scope
        matched: APIRoute | None = None
        for route in request.app.routes:
            if not isinstance(route, APIRoute):
                continue
            match, _ = route.matches(scope)
            if match == Match.FULL:
                matched = route
                break

        # Unmatched path under /api/admin: let FastAPI return its 404
        # so OpenAPI / explicit 405 responses are preserved.
        if matched is None:
            return await call_next(request)

        if admin_route_is_gated(matched):
            return await call_next(request)

        log.error(
            "admin.default_deny.missing_rbac_gate",
            path=path,
            method=request.method,
            endpoint=getattr(matched.endpoint, "__name__", "?"),
        )
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"code": "missing_rbac_gate"},
        )


__all__ = [
    "ADMIN_PUBLIC_MARKER",
    "AdminDefaultDenyMiddleware",
    "RBAC_DEP_MARKER",
    "admin_public_route",
    "admin_route_is_gated",
    "get_current_admin",
    "iter_admin_routes",
    "require_admin_role",
]
