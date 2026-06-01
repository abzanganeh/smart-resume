"""RBAC coverage assertion (IMPLEMENTATION_PLAN section 8.4.1).

CI fails if any route registered under ``/api/admin`` is missing the
``require_admin_role`` dependency AND is not explicitly marked with
``admin_public_route``.  This is the lint/test side of the
default-deny middleware so a missing gate is caught at PR time.
"""

from __future__ import annotations

import pytest

from app.dependencies.admin_auth import (
    admin_route_is_gated,
    iter_admin_routes,
)
from app.main import app


def test_all_admin_routes_are_gated() -> None:
    routes = list(iter_admin_routes(app))
    assert routes, "expected at least one /api/admin/* route registered"
    ungated = [r for r in routes if not admin_route_is_gated(r)]
    if ungated:
        pretty = "\n".join(
            f"  {sorted(r.methods)[0]} {r.path}  (handler: {r.endpoint.__name__})"
            for r in ungated
        )
        pytest.fail(
            "The following admin routes are missing require_admin_role "
            "and are not marked admin_public_route. Default-deny would "
            "block them at runtime, but CI must catch the gap at "
            f"merge time:\n{pretty}"
        )


def test_no_admin_routes_outside_api_admin_prefix() -> None:
    """Every route that imports require_admin_role must live under /api/admin.

    This is a defensive check: the default-deny middleware only fires
    on /api/admin/*, so a require_admin_role attached elsewhere would
    silently still rely on the dep itself but bypass the middleware.
    """
    from fastapi.routing import APIRoute

    from app.dependencies.admin_auth import RBAC_DEP_MARKER

    bad: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path.startswith("/api/admin"):
            continue
        stack = list(route.dependant.dependencies)
        while stack:
            sub = stack.pop()
            if sub.call is not None and getattr(sub.call, RBAC_DEP_MARKER, None):
                bad.append(f"{sorted(route.methods)[0]} {route.path}")
                break
            stack.extend(sub.dependencies)
    assert not bad, (
        "require_admin_role attached to non-admin route(s); these would "
        "bypass the /api/admin default-deny middleware: " + ", ".join(bad)
    )
