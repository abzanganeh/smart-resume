"""RBAC matrix tests (IMPLEMENTATION_PLAN section 8.4.1).

For a representative sample of routes from §6 "Admin", assert:

- The **required** role returns 200/201 (or another non-403/401 code).
- A **lower** role receives 403.
- **Anonymous** receives 401.

The §8.4.1 capability matrix is encoded as ``MATRIX`` below. It is
intentionally a hand-written subset rather than fuzzed across all 46
routes - some routes need fixture data that is expensive to set up.
The fixture-light routes still cover every capability row in §8.4.1.

NOTE: The default-deny middleware returns 403 for missing RBAC; here
we exercise the **dependency-side** rejection with a valid session
that has the wrong role.  Anonymous goes through the dep too and
returns 401 because no token is provided.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminRole
from tests.admin.conftest import issue_admin_session, make_admin


# Each tuple: (method, path, allowed_roles, denied_roles, expected_status_for_allowed)
# We expect 401 anonymous, 403 for denied roles, 200/201 (or 404 when
# row not found) for allowed roles.
MATRIX: list[tuple[str, str, set[AdminRole], set[AdminRole], int]] = [
    # Read endpoints (all 4 roles allowed)
    (
        "GET",
        "/api/admin/users",
        {AdminRole.super_admin, AdminRole.admin, AdminRole.support_agent, AdminRole.read_only_analyst},
        set(),
        200,
    ),
    (
        "GET",
        "/api/admin/plans",
        {AdminRole.super_admin, AdminRole.admin, AdminRole.support_agent, AdminRole.read_only_analyst},
        set(),
        200,
    ),
    (
        "GET",
        "/api/admin/feature-flags",
        {AdminRole.super_admin, AdminRole.admin, AdminRole.support_agent, AdminRole.read_only_analyst},
        set(),
        200,
    ),
    (
        "GET",
        "/api/admin/llm",
        {AdminRole.super_admin, AdminRole.admin, AdminRole.support_agent, AdminRole.read_only_analyst},
        set(),
        200,
    ),
    (
        "GET",
        "/api/admin/llm/steps",
        {AdminRole.super_admin, AdminRole.admin, AdminRole.support_agent, AdminRole.read_only_analyst},
        set(),
        200,
    ),
    (
        "GET",
        "/api/admin/audit-log",
        {AdminRole.super_admin, AdminRole.admin, AdminRole.support_agent, AdminRole.read_only_analyst},
        set(),
        200,
    ),
    (
        "GET",
        "/api/admin/refunds",
        {AdminRole.super_admin, AdminRole.admin, AdminRole.support_agent, AdminRole.read_only_analyst},
        set(),
        200,
    ),
    (
        "GET",
        "/api/admin/reports/overview",
        {AdminRole.super_admin, AdminRole.admin, AdminRole.support_agent, AdminRole.read_only_analyst},
        set(),
        200,
    ),
    # Mutations restricted to super-admin only
    (
        "POST",
        "/api/admin/feature-flags",
        {AdminRole.super_admin},
        {AdminRole.admin, AdminRole.support_agent, AdminRole.read_only_analyst},
        201,  # created
    ),
    (
        "POST",
        "/api/admin/auth/invite",
        {AdminRole.super_admin},
        {AdminRole.admin, AdminRole.support_agent, AdminRole.read_only_analyst},
        200,  # invite returns 200
    ),
    (
        "POST",
        "/api/admin/plans",
        {AdminRole.super_admin},
        {AdminRole.admin, AdminRole.support_agent, AdminRole.read_only_analyst},
        201,
    ),
    (
        "POST",
        "/api/admin/llm",
        {AdminRole.super_admin},
        {AdminRole.admin, AdminRole.support_agent, AdminRole.read_only_analyst},
        201,
    ),
    (
        "POST",
        "/api/admin/llm/steps",
        {AdminRole.super_admin},
        {AdminRole.admin, AdminRole.support_agent, AdminRole.read_only_analyst},
        201,
    ),
    # Credit adjustment - super-admin OR support-agent
    # We capture the dual permission elsewhere below (since the
    # MATRIX format only carries one allowed set we test the
    # support_agent path separately).
]


def _payload_for(method: str, path: str) -> dict | None:
    """Return a minimal valid JSON body for the given write route.

    For GET / DELETE we return None.  For POST / PATCH we provide just
    enough fields to satisfy the Pydantic validator so the request
    proceeds far enough to hit the dependency-side RBAC check.
    """
    if method != "POST":
        return None
    if path.endswith("/feature-flags"):
        return {
            "key": "rbac_matrix_flag",
            "description": "rbac matrix test",
            "enabled": False,
            "rollout_percent": 0,
            "visibility": "public",
        }
    if path.endswith("/auth/invite"):
        return {
            "email": "invite-target@example.com",
            "role": "admin",
            "display_name": "Test",
        }
    if path.endswith("/plans"):
        return {
            "code": "rbac_matrix_plan",
            "stripe_price_id": "price_rbac",
            "amount_cents": 100,
            "currency": "USD",
            "interval": "month",
        }
    if path.endswith("/llm"):
        return {
            "tier": "best",
            "provider": "openai",
            "model_string": "gpt-4o",
            "phases_enabled": [],
        }
    if path.endswith("/llm/steps"):
        return {
            "step": "chat",
            "provider": "openai",
            "model_string": "gpt-4o-mini",
        }
    return {}


@pytest.mark.parametrize(
    "method,path,allowed_roles,denied_roles,expected_status_for_allowed",
    MATRIX,
)
@pytest.mark.asyncio
async def test_rbac_matrix(
    db_session: AsyncSession,
    app_client: AsyncClient,
    method: str,
    path: str,
    allowed_roles: set[AdminRole],
    denied_roles: set[AdminRole],
    expected_status_for_allowed: int,
) -> None:
    # Anonymous -> 401
    anon = await app_client.request(method, path, json=_payload_for(method, path))
    assert anon.status_code == 401, (
        f"{method} {path}: anonymous should be 401, got {anon.status_code} {anon.text}"
    )

    # Build one admin per role and try the route once
    payload = _payload_for(method, path)

    for role in allowed_roles | denied_roles:
        admin, _ = await make_admin(
            db_session,
            email=f"{role.value.replace('-', '_')}-{path.replace('/', '_')}-{method}@x.com",
            role=role,
        )
        await db_session.commit()
        _, headers = await issue_admin_session(admin.id)

        body = payload
        # Make POST keys unique per role to avoid 409 collisions across
        # parametrize iterations.
        if isinstance(body, dict) and method == "POST":
            unique = role.value.replace("-", "_").lower()
            if "key" in body:
                body = {**body, "key": f"flag_{unique}_post"}
            if path.endswith("/plans"):
                body = {**body, "code": f"rbac_{unique}"}
            if path.endswith("/auth/invite"):
                body = {**body, "email": f"invitee_{unique}@example.com"}

        resp = await app_client.request(method, path, json=body, headers=headers)
        if role in allowed_roles:
            assert resp.status_code in {expected_status_for_allowed, 200}, (
                f"{method} {path} as {role.value}: expected "
                f"{expected_status_for_allowed}, got {resp.status_code} {resp.text}"
            )
        else:
            assert resp.status_code == 403, (
                f"{method} {path} as {role.value}: expected 403, "
                f"got {resp.status_code} {resp.text}"
            )


@pytest.mark.asyncio
async def test_credit_adjustment_super_admin_and_support_agent_only(
    db_session: AsyncSession, app_client: AsyncClient
) -> None:
    """Per §8.4.1 row 'Adjust user credits': super-admin AND support-agent.

    admin and read-only-analyst must receive 403.
    """
    import uuid as _uuid

    from app.models.user import AuthProvider, User, UserTier

    target = User(
        id=_uuid.uuid4(),
        email="creditee@example.com",
        display_name="Creditee",
        password_hash=None,
        tier=UserTier.free,
        auth_provider=AuthProvider.email,
    )
    db_session.add(target)
    await db_session.flush()

    payload = {"delta": 5, "credit_kind": "free", "reason": "test"}
    path = f"/api/admin/users/{target.id}/credits"

    for role, expect in (
        (AdminRole.super_admin, 200),
        (AdminRole.support_agent, 200),
        (AdminRole.admin, 403),
        (AdminRole.read_only_analyst, 403),
    ):
        admin, _ = await make_admin(
            db_session,
            email=f"credit-{role.value}@example.com",
            role=role,
        )
        await db_session.commit()
        _, headers = await issue_admin_session(admin.id)
        resp = await app_client.patch(path, json=payload, headers=headers)
        assert resp.status_code == expect, (
            f"{role.value}: expected {expect}, got {resp.status_code} {resp.text}"
        )


@pytest.mark.asyncio
async def test_audit_log_support_agent_only_sees_own(
    db_session: AsyncSession, app_client: AsyncClient
) -> None:
    """§8.4.1 footnote: support-agent only sees their own audit rows."""
    from app.services.admin_auth.audit import write_admin_audit

    other_admin, _ = await make_admin(
        db_session, email="other@example.com", role=AdminRole.super_admin
    )
    self_admin, _ = await make_admin(
        db_session, email="self@example.com", role=AdminRole.support_agent
    )
    await db_session.flush()

    # Write one audit row attributed to other_admin and another to self_admin
    await write_admin_audit(
        db_session,
        actor_admin_id=other_admin.id,
        action="other_action",
        target_kind="x",
        target_id="other-1",
    )
    await write_admin_audit(
        db_session,
        actor_admin_id=self_admin.id,
        action="self_action",
        target_kind="x",
        target_id="self-1",
    )
    await db_session.commit()

    _, headers = await issue_admin_session(self_admin.id)
    resp = await app_client.get("/api/admin/audit-log", headers=headers)
    assert resp.status_code == 200, resp.text
    actions = {r["action"] for r in resp.json()["items"]}
    assert "self_action" in actions
    assert "other_action" not in actions
