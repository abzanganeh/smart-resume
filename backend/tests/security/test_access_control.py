"""Broken access control regressions (OWASP A01) — slice A8.

Threat model
------------

Three distinct A01 failure modes, each with its own class of test below.

1. **A route ships without an auth gate.** The gate is a FastAPI
   dependency, so forgetting it is a silent omission: the handler still
   works, it just serves anyone.  Nothing in review reliably catches
   this, and the route inventory grows every milestone.  The inventory
   tests enumerate every registered route and force each new
   unauthenticated one through an explicit, reasoned allowlist entry.

2. **The gate is present but the query is not scoped (IDOR).** The
   handler authenticates the caller and then loads a row by id without
   an owner predicate.  This leaks résumé text, application history and
   billing records between tenants with nothing but an id guess.  The
   IDOR tests always assert both directions: the owner gets 200 and the
   stranger does not, so a passing test cannot mean "the fixture never
   persisted".

3. **Admin RBAC degrades to "any admin".** §8.4.1 assigns a specific
   role set per capability.  ``require_admin_role`` carries that set as
   a marker, so the matrix here is *generated* from the live routes
   rather than hand-written — a new admin route is covered the moment
   it is registered.

Relationship to existing suites
-------------------------------

- ``tests/admin/test_rbac_coverage.py`` proves every ``/api/admin``
  route *has* a gate (static).  This module proves the gate *rejects*
  (runtime), for every route rather than a curated sample.
- ``tests/admin/test_rbac_matrix.py`` pins the exact §8.4.1 role set for
  a hand-picked subset, including allowed-role happy paths that need
  fixture data.  The generated matrix here only asserts the deny side,
  which needs no fixtures and therefore scales to all routes.

CI note
-------

The inventory and anonymous-rejection tests deliberately avoid the
database, so they still run wherever no Postgres is configured.  The
IDOR and admin-role tests are marked ``integration`` and need one; the
``backend-security`` CI job runs a pgvector service and exports
``DATABASE_URL``, so both groups execute there.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.dependencies.admin_auth import RBAC_DEP_MARKER
from app.main import app
from app.models.admin import AdminRole
from app.models.dashboard import ResumeRecord, ResumeRecordStatus
from app.models.user import CreditTransaction
from app.services.session_store import create_session, get_session, update_session
from tests.admin.conftest import issue_admin_session, make_admin

# Dependencies that establish an authenticated principal.  A route whose
# dependency tree contains none of these — and no ``require_admin_role``
# marker — is reachable by anyone on the internet.
AUTH_DEPENDENCY_NAMES = frozenset(
    {
        "get_current_user",
        "get_current_user_id",
        "get_current_admin",
    }
)


# ---------------------------------------------------------------------------
# Route introspection helpers
# ---------------------------------------------------------------------------


def _api_routes() -> list[APIRoute]:
    return [r for r in app.routes if isinstance(r, APIRoute)]


def _dependency_names(route: APIRoute) -> set[str]:
    """Names of every callable in ``route``'s transitive dependency tree.

    ``require_admin_role`` returns a locally-defined closure whose
    ``__name__`` is uninformative, so it is reported as the sentinel
    ``"__RBAC__"`` via the marker attribute the dependency factory sets.
    """
    found: set[str] = set()
    stack = list(route.dependant.dependencies)
    while stack:
        sub = stack.pop()
        if sub.call is not None:
            found.add(getattr(sub.call, "__name__", repr(sub.call)))
            if getattr(sub.call, RBAC_DEP_MARKER, None) is not None:
                found.add("__RBAC__")
        stack.extend(sub.dependencies)
    return found


def _is_gated(route: APIRoute) -> bool:
    names = _dependency_names(route)
    return bool(names & AUTH_DEPENDENCY_NAMES) or "__RBAC__" in names


def _required_admin_roles(route: APIRoute) -> frozenset[str] | None:
    """The ``__admin_role_dep__`` role set for an RBAC-gated route."""
    stack = list(route.dependant.dependencies)
    while stack:
        sub = stack.pop()
        if sub.call is not None:
            marker = getattr(sub.call, RBAC_DEP_MARKER, None)
            if marker is not None:
                return frozenset(marker)
        stack.extend(sub.dependencies)
    return None


def _request_targets(route: APIRoute) -> list[tuple[str, str]]:
    """``(method, path)`` pairs worth probing, skipping HEAD/OPTIONS."""
    return [
        (method, route.path)
        for method in sorted(route.methods)
        if method not in {"HEAD", "OPTIONS"}
    ]


_PATH_PARAM = re.compile(r"\{[^}]+\}")
# Any well-formed UUID works: the auth gate must reject before the
# handler ever looks the id up.
_PLACEHOLDER_ID = "00000000-0000-4000-8000-000000000000"


def _concrete_path(path: str) -> str:
    return _PATH_PARAM.sub(_PLACEHOLDER_ID, path)


# ---------------------------------------------------------------------------
# The public-route allowlist
# ---------------------------------------------------------------------------

# Every route reachable without an authenticated principal, with the
# reason it is allowed to be.  Adding a route to this map is a security
# decision and should be reviewed as one.
#
# The anonymous tailoring flow (``/api/sessions/*``) is the largest
# entry: TalioCV lets a visitor tailor a résumé before signing up, and
# the opaque uuid4 ``session_id`` is the only capability protecting it.
# That is a deliberate product trade-off, not an oversight — see the
# session-capability tests at the bottom of this module for the
# properties it depends on.
PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    # --- infrastructure -------------------------------------------------
    ("GET", "/health"): "liveness probe; no user data",
    # --- credential establishment ---------------------------------------
    ("POST", "/api/auth/register"): "creates the principal",
    ("POST", "/api/auth/login"): "establishes the principal",
    ("POST", "/api/auth/refresh"): "authenticated by the refresh cookie",
    ("POST", "/api/auth/callback"): "OAuth provider callback",
    ("POST", "/api/auth/2fa/verify"): "authenticated by the 2FA challenge token",
    ("POST", "/api/auth/password/forgot"): "pre-credential; responses are uniform",
    ("POST", "/api/auth/password/reset"): "authenticated by the reset token",
    ("GET", "/api/auth/verify/{token}"): "authenticated by the emailed token",
    ("POST", "/api/auth/extension/login"): "establishes the extension principal",
    ("POST", "/api/auth/extension/refresh"): "authenticated by the extension refresh token",
    ("POST", "/api/auth/extension/callback"): "extension OAuth callback",
    # --- admin credential establishment (marked admin_public_route) -----
    ("POST", "/api/admin/auth/login"): "establishes the admin principal",
    ("POST", "/api/admin/auth/2fa/verify"): "authenticated by the admin challenge token",
    ("POST", "/api/admin/auth/2fa/enroll"): "authenticated by the admin setup token",
    ("POST", "/api/admin/auth/accept-invite"): "authenticated by the invite token",
    # --- webhooks (verified by provider signature, not by session) ------
    ("POST", "/api/webhooks/stripe"): "Stripe signature verification; see test_exceptional_conditions",
    ("POST", "/api/notifications/webhooks/resend"): "Resend signature verification",
    # --- scheduler (shared secret, not a user session) ------------------
    ("DELETE", "/api/account"): "X-Scheduler-Secret shared secret; covered below",
    (
        "POST",
        "/api/auth/scheduler/unverified-cleanup",
    ): "X-Scheduler-Secret shared secret; covered below",
    # --- public runtime config (no user data) ---------------------------
    ("GET", "/api/auth/register-config"): "public Turnstile site key",
    ("GET", "/api/feature-flags"): "public runtime config",
    ("GET", "/api/announcements"): "public runtime config",
    ("GET", "/api/billing/prices"): "public price list",
    ("GET", "/api/billing/free-tier"): "public signup-grant size",
    (
        "GET",
        "/api/billing/offers/{code}",
    ): "public offer metadata for marketing popups; stripe_promotion_code_id omitted",
    ("GET", "/api/llm/providers"): "static provider catalogue",
    # --- marketing / legal ----------------------------------------------
    ("POST", "/api/legal/dpo-contact"): "public DPO contact form",
    ("GET", "/api/interview-questions"): "public marketing content",
    ("GET", "/api/interview-questions/stats"): "public marketing content",
    ("POST", "/api/checkup"): "public try-before-signup checkup; IP rate limited",
    # --- Flint handoff (redeems a single-use handoff token) --------------
    ("POST", "/api/flint/context"): "authenticated by the single-use handoff token",
    # --- anonymous tailoring flow (session_id is the capability) --------
    ("POST", "/api/sessions"): "mints the anonymous session capability",
    ("GET", "/api/sessions/{session_id}"): "anonymous tailoring flow",
    ("POST", "/api/sessions/{session_id}/resume"): "anonymous tailoring flow",
    ("POST", "/api/sessions/{session_id}/resume/text"): "anonymous tailoring flow",
    ("PATCH", "/api/sessions/{session_id}/resume/tailored"): "anonymous tailoring flow",
    ("GET", "/api/sessions/{session_id}/resume/versions"): "anonymous tailoring flow",
    (
        "POST",
        "/api/sessions/{session_id}/resume/versions/{snapshot_id}/restore",
    ): "anonymous tailoring flow",
    ("POST", "/api/sessions/{session_id}/userinfo"): "anonymous tailoring flow",
    ("POST", "/api/sessions/{session_id}/jd"): "anonymous tailoring flow",
    ("GET", "/api/sessions/{session_id}/export"): "anonymous tailoring flow",
    ("POST", "/api/sessions/{session_id}/audit"): "anonymous tailoring flow",
    ("PATCH", "/api/sessions/{session_id}/audit"): "anonymous tailoring flow",
    (
        "POST",
        "/api/sessions/{session_id}/audit/suggest-bullet-fixes",
    ): "anonymous tailoring flow",
    ("PATCH", "/api/sessions/{session_id}/additions"): "anonymous tailoring flow",
    ("PATCH", "/api/sessions/{session_id}/approved-metrics"): "anonymous tailoring flow",
    ("PATCH", "/api/sessions/{session_id}/tailored"): "anonymous tailoring flow",
    ("POST", "/api/sessions/{session_id}/tailored/commit"): "anonymous tailoring flow",
    ("POST", "/api/sessions/{session_id}/chat"): "anonymous tailoring flow",
    ("GET", "/api/sessions/{session_id}/cover-letter"): "anonymous tailoring flow",
    ("POST", "/api/sessions/{session_id}/cover-letter"): "anonymous tailoring flow",
    ("GET", "/api/sessions/{session_id}/cover-letter/export"): "anonymous tailoring flow",
    ("POST", "/api/sessions/{session_id}/phases/{phase}/run"): "anonymous tailoring flow",
    ("GET", "/api/sessions/{session_id}/phases/{phase}/events"): "anonymous tailoring flow",
}

# Routes intentionally hidden from the OpenAPI schema.  A hidden route is
# strictly more dangerous than a documented one — nobody reviewing the
# schema will notice it — so the set is pinned rather than inferred.
HIDDEN_FROM_SCHEMA: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/webhooks/stripe"),
        ("POST", "/api/notifications/webhooks/resend"),
    }
)


# ---------------------------------------------------------------------------
# 1. Route inventory (no database)
# ---------------------------------------------------------------------------


def test_every_route_is_gated_or_explicitly_public() -> None:
    """A new route must either carry an auth gate or be allowlisted.

    This is the test that catches the actual A01 regression we are
    worried about: someone adds a handler, forgets the ``user`` argument,
    and ships a route that serves any caller.  Failure output names the
    route and the fix so it is actionable without reading this file.
    """
    undeclared: list[str] = []
    for route in _api_routes():
        if _is_gated(route):
            continue
        for method, path in _request_targets(route):
            if (method, path) not in PUBLIC_ROUTES:
                undeclared.append(f"  {method} {path}  (handler: {route.endpoint.__name__})")

    assert not undeclared, (
        "These routes have no authentication dependency and are not in "
        "PUBLIC_ROUTES. Either add an auth dependency, or add an entry to "
        "PUBLIC_ROUTES stating why anonymous access is correct:\n"
        + "\n".join(sorted(undeclared))
    )


def test_public_allowlist_has_no_stale_entries() -> None:
    """The allowlist must describe reality, or it silently stops working.

    Two ways it rots: an entry for a route that no longer exists (dead
    weight that hides nothing), and an entry for a route that has since
    *gained* an auth gate (which would let a future regression removing
    that gate pass unnoticed).  Both are failures.
    """
    live: dict[tuple[str, str], APIRoute] = {}
    for route in _api_routes():
        for target in _request_targets(route):
            live[target] = route

    removed = sorted(f"  {m} {p}" for (m, p) in PUBLIC_ROUTES if (m, p) not in live)
    assert not removed, (
        "PUBLIC_ROUTES references routes that no longer exist; delete "
        "these entries:\n" + "\n".join(removed)
    )

    now_gated = sorted(
        f"  {m} {p}" for (m, p) in PUBLIC_ROUTES if _is_gated(live[(m, p)])
    )
    assert not now_gated, (
        "These routes are allowlisted as public but now carry an auth "
        "gate. Remove them from PUBLIC_ROUTES so a future regression that "
        "drops the gate fails this suite:\n" + "\n".join(now_gated)
    )


def test_openapi_documents_every_route_except_pinned_hidden_ones() -> None:
    """Enumerate from ``app.openapi()`` and reconcile against the router table.

    ``app.openapi()`` is what an auditor reads, so anything missing from
    it is invisible to review.  Reconciling the two enumerations means a
    new ``include_in_schema=False`` route has to be justified here.
    """
    schema = app.openapi()
    documented = {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
    }
    registered = {
        target for route in _api_routes() for target in _request_targets(route)
    }

    hidden = registered - documented
    assert hidden == HIDDEN_FROM_SCHEMA, (
        "The set of routes hidden from the OpenAPI schema changed. "
        f"Unexpectedly hidden: {sorted(hidden - HIDDEN_FROM_SCHEMA)}; "
        f"no longer hidden: {sorted(HIDDEN_FROM_SCHEMA - hidden)}"
    )


def test_openapi_declares_a_security_scheme_for_gated_routes() -> None:
    """Gated routes must advertise their bearer scheme in the schema.

    A gated route that documents no security requirement misleads every
    consumer of the schema — SDK generators, the frontend client, and
    any auditor reading it — into believing it is public.
    """
    schema = app.openapi()
    missing: list[str] = []
    for route in _api_routes():
        if not _is_gated(route):
            continue
        for method, path in _request_targets(route):
            operation = schema["paths"].get(path, {}).get(method.lower())
            if operation is None:
                continue  # hidden routes are reconciled by the test above
            if not operation.get("security"):
                missing.append(f"  {method} {path}")

    assert not missing, (
        "These routes are gated at runtime but declare no security scheme "
        "in the OpenAPI document:\n" + "\n".join(sorted(missing))
    )


# ---------------------------------------------------------------------------
# 2. Anonymous rejection, live fire (no database)
# ---------------------------------------------------------------------------


class _PoisonedSession:
    """Stand-in for ``AsyncSession`` that fails if anything touches it.

    The point is not just that anonymous callers get a 401 — it is that
    they get one *before* the handler reaches the database.  A route that
    queried first and checked authorization afterwards would still
    return 401 while having already done unauthenticated work, so a
    plain status-code assertion would miss it.
    """

    def __getattr__(self, name: str):
        raise AssertionError(
            f"an unauthenticated request reached the database (AsyncSession.{name})"
        )


@pytest_asyncio.fixture()
async def anonymous_client() -> AsyncGenerator[AsyncClient, None]:
    """Client with no credentials and a database that must not be used."""

    async def _override_db() -> AsyncGenerator[_PoisonedSession, None]:
        yield _PoisonedSession()

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


def _gated_targets() -> list[tuple[str, str]]:
    return sorted(
        target
        for route in _api_routes()
        if _is_gated(route)
        for target in _request_targets(route)
    )


@pytest.mark.parametrize("method,path", _gated_targets())
async def test_gated_route_rejects_anonymous_request(
    anonymous_client: AsyncClient, method: str, path: str
) -> None:
    """Every gated route answers 401 to a credential-less request.

    Parametrized per route rather than looped so a regression names the
    offending route in the failure list instead of hiding behind the
    first assertion that trips.
    """
    response = await anonymous_client.request(method, _concrete_path(path), json={})
    assert response.status_code == 401, (
        f"{method} {path}: anonymous request should be 401, got "
        f"{response.status_code} {response.text[:400]}"
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("DELETE", "/api/account"),
        ("POST", "/api/auth/scheduler/unverified-cleanup"),
    ],
)
async def test_scheduler_route_rejects_missing_and_wrong_secret(
    anonymous_client: AsyncClient, method: str, path: str
) -> None:
    """Scheduler ticks are gated by a shared secret, not a user session.

    They sit in ``PUBLIC_ROUTES`` because they have no user principal,
    which excludes them from the anonymous sweep above — so they need
    their own assertion. Both drive destructive maintenance work
    (account closure, unverified-account suspension), so an unguarded
    version would let anyone trigger it.
    """
    for headers in ({}, {"X-Scheduler-Secret": "not-the-secret"}):
        response = await anonymous_client.request(method, path, headers=headers)
        assert response.status_code == 401, (
            f"{method} {path} with headers={headers} should be 401, got "
            f"{response.status_code} {response.text[:200]}"
        )


# ---------------------------------------------------------------------------
# 3. Admin RBAC matrix, generated from §8.4.1 markers
# ---------------------------------------------------------------------------


def _admin_deny_cases() -> list[tuple[str, str, str, frozenset[str]]]:
    """``(method, path, denied_role, allowed_roles)`` for each admin route.

    The denied role is read off the route's own ``require_admin_role``
    marker, so the matrix cannot drift from §8.4.1 as routes are added.
    Routes that legitimately allow all four roles (the read-only rows of
    the matrix) contribute no deny case.
    """
    all_roles = frozenset(r.value for r in AdminRole)
    cases: list[tuple[str, str, str, frozenset[str]]] = []
    for route in _api_routes():
        if not route.path.startswith("/api/admin"):
            continue
        allowed = _required_admin_roles(route)
        if allowed is None:
            continue  # admin_public_route; covered by PUBLIC_ROUTES
        deniable = sorted(all_roles - allowed)
        if not deniable:
            continue
        for method, path in _request_targets(route):
            cases.append((method, path, deniable[0], allowed))
    return cases


_ADMIN_DENY_CASES = _admin_deny_cases()


@pytest.mark.integration
@pytest.mark.parametrize(
    "method,path,denied_role,allowed_roles",
    _ADMIN_DENY_CASES,
    ids=[f"{m}-{p}-as-{d}" for m, p, d, _ in _ADMIN_DENY_CASES],
)
async def test_admin_route_denies_role_outside_its_allowlist(
    db_session: AsyncSession,
    app_client: AsyncClient,
    method: str,
    path: str,
    denied_role: str,
    allowed_roles: frozenset[str],
) -> None:
    """A fully authenticated admin with the wrong role gets 403, not 200.

    ``require_admin_role`` rejects before the handler runs, so no
    fixture data is needed and the check scales to every admin route —
    including the ones ``test_rbac_matrix.py`` skips because their happy
    path is expensive to set up.

    An empty body is enough: a 422 here would mean the request reached
    body validation, i.e. it got *past* the role gate, which is exactly
    the regression this asserts against.
    """
    admin, _ = await make_admin(
        db_session,
        email=f"deny-{uuid.uuid4().hex[:12]}@example.com",
        role=AdminRole(denied_role),
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    response = await app_client.request(
        method, _concrete_path(path), json={}, headers=headers
    )
    assert response.status_code == 403, (
        f"{method} {path} as {denied_role}: expected 403 (allowed roles: "
        f"{sorted(allowed_roles)}), got {response.status_code} "
        f"{response.text[:300]}"
    )


@pytest.mark.integration
async def test_admin_session_token_is_rejected_on_user_routes(
    db_session: AsyncSession, app_client: AsyncClient
) -> None:
    """An admin session must not be usable as a user session.

    The two token types are minted by different services with different
    claims.  If ``get_current_user`` ever accepted an admin token, every
    admin would silently gain a user principal whose id is an
    ``admin_users`` row — which no ownership predicate would match, but
    which also must never authenticate.
    """
    admin, _ = await make_admin(
        db_session,
        email=f"crossuse-{uuid.uuid4().hex[:12]}@example.com",
        role=AdminRole.super_admin,
    )
    await db_session.commit()
    _, headers = await issue_admin_session(admin.id)

    response = await app_client.get("/api/resumes", headers=headers)
    assert response.status_code == 401, (
        "an admin session token must not authenticate a user route, got "
        f"{response.status_code} {response.text[:200]}"
    )


# ---------------------------------------------------------------------------
# 4. IDOR — user A must not reach user B's rows
# ---------------------------------------------------------------------------

_PASSWORD = "tr0ub4dor&3sandwich-eats-paint"


@pytest.fixture()
def stub_turnstile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the signup CAPTCHA for the IDOR fixtures.

    The default Turnstile secret is Cloudflare's always-pass dummy key,
    so a real ``/api/auth/register`` call reaches
    ``challenges.cloudflare.com``. These are access-control tests, not
    bot-defence tests — Turnstile is M20's control and is covered by
    ``tests/unit/test_turnstile.py`` — so the suite should not fail
    because the network is unavailable.
    """
    monkeypatch.setattr(
        "app.routers.auth.verify_turnstile_token",
        AsyncMock(return_value=True),
    )


async def _register(client: AsyncClient, label: str) -> tuple[str, uuid.UUID]:
    """Register a user through the real endpoint and return its credentials."""
    payload = {
        "email": f"{label}-{uuid.uuid4().hex[:10]}@example.com",
        "password": _PASSWORD,
        "display_name": label,
        "accepted_tos_version": "2026-06",
        "marketing_opt_in": False,
        "turnstile_token": "test-turnstile-token",
    }
    response = await client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    return body["access_token"], uuid.UUID(body["user"]["id"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_resume_record(
    db: AsyncSession, user_id: uuid.UUID, *, session_id: str | None = None
) -> ResumeRecord:
    record = ResumeRecord(
        id=uuid.uuid4(),
        user_id=user_id,
        session_id=session_id or f"sess-{uuid.uuid4().hex[:8]}",
        jd_title="Staff Backend Engineer",
        jd_company="Northwind Systems",
        jd_text_hash=uuid.uuid4().hex,
        tags=[],
        current_ats_score=81,
        starting_ats_score=74,
        status=ResumeRecordStatus.draft,
    )
    db.add(record)
    await db.flush()
    await db.commit()
    return record


async def _create_application(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/api/applications",
        json={"jd_title": "Staff Backend Engineer", "jd_company": "Northwind Systems"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest_asyncio.fixture()
async def two_users(
    app_client: AsyncClient, stub_turnstile: None
) -> tuple[tuple[str, uuid.UUID], tuple[str, uuid.UUID]]:
    """Victim (A) and attacker (B), both fully authenticated."""
    victim = await _register(app_client, "victim")
    attacker = await _register(app_client, "attacker")
    return victim, attacker


@pytest.mark.integration
@pytest.mark.parametrize(
    "method,suffix",
    [
        ("GET", ""),
        ("PATCH", ""),
        ("DELETE", ""),
        ("GET", "/scores"),
        ("GET", "/download"),
        ("POST", "/duplicate"),
    ],
)
async def test_resume_record_is_not_reachable_by_another_user(
    app_client: AsyncClient,
    db_session: AsyncSession,
    two_users: tuple[tuple[str, uuid.UUID], tuple[str, uuid.UUID]],
    method: str,
    suffix: str,
) -> None:
    """Résumé records are the crown jewels: full CV text, company, scores.

    Covers the whole ``/api/resumes/{record_id}`` family in one sweep
    because they share ``_get_owned_record``; if that predicate ever
    loses its ``user_id`` term, every one of them leaks at once.

    The assertion is on the *ownership* outcome rather than on success,
    because some routes in the family need more fixture state than a
    bare record (``/download`` wants tailored output, ``/duplicate``
    wants a live session).  Those legitimately fail for the owner too —
    with 410/422, not 403/404.  Distinguishing "found but incomplete"
    from "not yours" is exactly the signal this test needs, and it keeps
    the positive control honest: a 404 for the attacker cannot be
    explained away by a missing fixture, because the owner's request
    proved the row is there.
    """
    denial_codes = {403, 404}
    (victim_token, victim_id), (attacker_token, _) = two_users
    record = await _seed_resume_record(db_session, victim_id)
    path = f"/api/resumes/{record.id}{suffix}"

    owner = await app_client.request(method, path, json={}, headers=_auth(victim_token))
    assert owner.status_code not in denial_codes, (
        f"{method} {path} as the owner must reach the row, got "
        f"{owner.status_code} {owner.text[:300]} — the IDOR assertion "
        "below would be vacuous"
    )

    attacker = await app_client.request(
        method, path, json={}, headers=_auth(attacker_token)
    )
    assert attacker.status_code in denial_codes, (
        f"{method} {path} as a different user must be denied, got "
        f"{attacker.status_code} {attacker.text[:300]}"
    )
    assert "Northwind Systems" not in attacker.text


@pytest.mark.integration
async def test_resume_record_patch_by_another_user_does_not_mutate(
    app_client: AsyncClient,
    db_session: AsyncSession,
    two_users: tuple[tuple[str, uuid.UUID], tuple[str, uuid.UUID]],
) -> None:
    """A denied write must also be a write that did not happen.

    Status codes can lie: a handler that mutates and *then* fails
    authorization returns 403 while the row is already changed.
    """
    (_, victim_id), (attacker_token, _) = two_users
    record = await _seed_resume_record(db_session, victim_id)
    original_name = record.display_name

    response = await app_client.patch(
        f"/api/resumes/{record.id}",
        json={"display_name": "owned-by-attacker", "tags": ["pwned"]},
        headers=_auth(attacker_token),
    )
    assert response.status_code in {403, 404}, response.text

    await db_session.refresh(record)
    assert record.display_name == original_name
    assert record.tags == []


@pytest.mark.integration
async def test_resume_record_delete_by_another_user_does_not_soft_delete(
    app_client: AsyncClient,
    db_session: AsyncSession,
    two_users: tuple[tuple[str, uuid.UUID], tuple[str, uuid.UUID]],
) -> None:
    """The idempotent-delete branch must not become an unscoped delete.

    ``delete_resume`` returns 200 when the row is already gone, which is
    the kind of forgiving branch that quietly turns into "deleted
    someone else's row" if the owner predicate is dropped from either
    query.
    """
    (_, victim_id), (attacker_token, _) = two_users
    record = await _seed_resume_record(db_session, victim_id)

    response = await app_client.delete(
        f"/api/resumes/{record.id}", headers=_auth(attacker_token)
    )
    assert response.status_code in {403, 404}, response.text

    await db_session.refresh(record)
    assert record.deleted_at is None, "attacker's DELETE soft-deleted the victim's row"


@pytest.mark.integration
async def test_resume_list_is_scoped_to_the_caller(
    app_client: AsyncClient,
    db_session: AsyncSession,
    two_users: tuple[tuple[str, uuid.UUID], tuple[str, uuid.UUID]],
) -> None:
    """Collection endpoints leak in bulk, so they get their own test."""
    (victim_token, victim_id), (attacker_token, _) = two_users
    record = await _seed_resume_record(db_session, victim_id)

    owner = await app_client.get("/api/resumes", headers=_auth(victim_token))
    assert owner.status_code == 200, owner.text
    assert str(record.id) in owner.text, "positive control: owner must see own record"

    attacker = await app_client.get("/api/resumes", headers=_auth(attacker_token))
    assert attacker.status_code == 200, attacker.text
    assert str(record.id) not in attacker.text


@pytest.mark.integration
@pytest.mark.parametrize(
    "method,suffix",
    [
        ("GET", ""),
        ("PATCH", ""),
        ("DELETE", ""),
        ("POST", "/archive"),
        ("POST", "/unarchive"),
        ("GET", "/reminders"),
        ("POST", "/rounds"),
    ],
)
async def test_tracker_application_is_not_reachable_by_another_user(
    app_client: AsyncClient,
    two_users: tuple[tuple[str, uuid.UUID], tuple[str, uuid.UUID]],
    method: str,
    suffix: str,
) -> None:
    """Application tracker rows expose where the victim is interviewing.

    Unlike the résumé family these handlers each run their own query, so
    the sweep is over the routes an attacker would actually try rather
    than over one shared helper.
    """
    (victim_token, _), (attacker_token, _) = two_users
    application_id = await _create_application(app_client, victim_token)
    path = f"/api/applications/{application_id}{suffix}"

    attacker = await app_client.request(
        method, path, json={}, headers=_auth(attacker_token)
    )
    assert attacker.status_code in {403, 404, 422}, (
        f"{method} {path} as a different user must be denied, got "
        f"{attacker.status_code} {attacker.text[:300]}"
    )
    # 422 is only acceptable as "body rejected before the row was
    # reached"; it must never come with the victim's data attached.
    assert "Northwind Systems" not in attacker.text


@pytest.mark.integration
async def test_tracker_application_list_is_scoped_to_the_caller(
    app_client: AsyncClient,
    two_users: tuple[tuple[str, uuid.UUID], tuple[str, uuid.UUID]],
) -> None:
    (victim_token, _), (attacker_token, _) = two_users
    application_id = await _create_application(app_client, victim_token)

    owner = await app_client.get("/api/applications", headers=_auth(victim_token))
    assert owner.status_code == 200, owner.text
    assert application_id in owner.text, "positive control: owner must see own row"

    attacker = await app_client.get("/api/applications", headers=_auth(attacker_token))
    assert attacker.status_code == 200, attacker.text
    assert application_id not in attacker.text


@pytest.mark.integration
async def test_session_resume_record_lookup_is_scoped_to_the_caller(
    app_client: AsyncClient,
    db_session: AsyncSession,
    two_users: tuple[tuple[str, uuid.UUID], tuple[str, uuid.UUID]],
) -> None:
    """The session→record bridge must scope on the caller, not the session.

    ``GET /api/sessions/{session_id}/resume-record`` takes an
    unauthenticated-flow identifier (the session id) and returns an
    authenticated-flow row. That seam is where "look up by session_id"
    is the tempting implementation, and it would hand any holder of a
    session id the owner's dashboard record.
    """
    (victim_token, victim_id), (attacker_token, _) = two_users
    shared_session_id = f"sess-{uuid.uuid4().hex[:12]}"
    await _seed_resume_record(db_session, victim_id, session_id=shared_session_id)

    owner = await app_client.get(
        f"/api/sessions/{shared_session_id}/resume-record",
        headers=_auth(victim_token),
    )
    assert owner.status_code == 200, owner.text

    attacker = await app_client.get(
        f"/api/sessions/{shared_session_id}/resume-record",
        headers=_auth(attacker_token),
    )
    assert attacker.status_code == 404, attacker.text
    assert "Northwind Systems" not in attacker.text


@pytest.mark.integration
async def test_credit_ledger_is_scoped_to_the_caller(
    app_client: AsyncClient,
    db_session: AsyncSession,
    two_users: tuple[tuple[str, uuid.UUID], tuple[str, uuid.UUID]],
) -> None:
    """Billing history is per-user; the ledger is the source of truth (§7.5).

    Registration grants both users a row, so a missing ``user_id``
    predicate shows up as the attacker seeing the victim's transaction
    id — not merely as a wrong count.
    """
    (victim_token, victim_id), (attacker_token, attacker_id) = two_users

    victim_rows = (
        await db_session.execute(
            select(CreditTransaction.id).where(CreditTransaction.user_id == victim_id)
        )
    ).scalars().all()
    assert victim_rows, "registration should have granted the victim credits"
    victim_tx_ids = {str(r) for r in victim_rows}

    owner = await app_client.get(
        "/api/credits/transactions", headers=_auth(victim_token)
    )
    assert owner.status_code == 200, owner.text
    assert {i["id"] for i in owner.json()["items"]} == victim_tx_ids

    attacker = await app_client.get(
        "/api/credits/transactions", headers=_auth(attacker_token)
    )
    assert attacker.status_code == 200, attacker.text
    attacker_ids = {i["id"] for i in attacker.json()["items"]}
    assert attacker_ids & victim_tx_ids == set()


@pytest.mark.integration
async def test_credit_balance_is_scoped_to_the_caller(
    app_client: AsyncClient,
    db_session: AsyncSession,
    two_users: tuple[tuple[str, uuid.UUID], tuple[str, uuid.UUID]],
) -> None:
    """A balance read must project the caller's ledger, not a global sum.

    Granting the victim a distinctive top-up makes an unscoped
    ``SUM(delta)`` visible: the attacker's balance would move.
    """
    from app.models.billing import CreditKind
    from app.services.billing.credits import grant_credit

    (_, victim_id), (attacker_token, _) = two_users

    before = await app_client.get("/api/credits/balance", headers=_auth(attacker_token))
    assert before.status_code == 200, before.text

    await grant_credit(
        db_session,
        user_id=victim_id,
        credit_kind=CreditKind.free,
        delta=97,
        reason="admin_grant",
    )
    await db_session.commit()

    after = await app_client.get("/api/credits/balance", headers=_auth(attacker_token))
    assert after.status_code == 200, after.text
    assert after.json() == before.json(), (
        "the victim's grant changed the attacker's balance — the balance "
        "projection is not scoped to the caller"
    )


@pytest.mark.integration
async def test_refund_request_cannot_target_another_users_subscription(
    app_client: AsyncClient,
    db_session: AsyncSession,
    two_users: tuple[tuple[str, uuid.UUID], tuple[str, uuid.UUID]],
) -> None:
    """A refund request must bind to the caller's own subscription.

    The payload carries Stripe identifiers, so the handler must resolve
    the subscription from the session principal rather than trusting
    anything the client sends. A ``RefundRecord`` attributed to the
    victim would put a stranger's refund into the victim's billing
    history and admin queue.
    """
    from app.models.billing import RefundRecord

    (_, victim_id), (attacker_token, attacker_id) = two_users

    response = await app_client.post(
        "/api/subscriptions/refund-request",
        json={
            "reason": "other",
            "note": "idor probe",
            "amount_usd": 19,
            "within_24h": False,
        },
        headers=_auth(attacker_token),
    )
    assert response.status_code in {200, 400, 402, 404, 409, 422}, response.text

    victim_records = (
        await db_session.execute(
            select(RefundRecord).where(RefundRecord.user_id == victim_id)
        )
    ).scalars().all()
    assert victim_records == [], (
        "the attacker's refund request created a RefundRecord attributed "
        "to the victim"
    )


# ---------------------------------------------------------------------------
# 5. The anonymous session capability
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_authenticated_session_rejects_a_different_bearer(
    app_client: AsyncClient,
    two_users: tuple[tuple[str, uuid.UUID], tuple[str, uuid.UUID]],
) -> None:
    """Once a session is claimed, another user's token must not drive it.

    Sessions start anonymous and become owned the first time an
    authenticated caller touches one (``resolve_bearer_user_id``).
    Without the mismatch check, a leaked session id would let a second
    account take over an in-flight tailoring session — and, because
    Phase 3 retrieval keys off ``session.user_id``, pull the original
    owner's résumé corpus into its own output.
    """
    (victim_token, victim_id), (attacker_token, _) = two_users

    created = await app_client.post("/api/sessions", headers=_auth(victim_token))
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]

    hijack = await app_client.post(
        f"/api/sessions/{session_id}/phases/1/run",
        json={},
        headers=_auth(attacker_token),
    )
    assert hijack.status_code == 403, (
        "a different user's bearer token must not be accepted for a "
        f"claimed session, got {hijack.status_code} {hijack.text[:300]}"
    )


@pytest.mark.integration
async def test_commit_tailored_rejects_a_different_bearer(
    app_client: AsyncClient,
    two_users: tuple[tuple[str, uuid.UUID], tuple[str, uuid.UUID]],
) -> None:
    """``commit_tailored`` must not overwrite ``user_id`` from a mismatched bearer.

    Before B2 this route read ``claims['sub']`` directly, bypassing the
    session ownership check that ``resolve_bearer_user_id`` enforces.
    """
    (victim_token, _), (attacker_token, _) = two_users
    minimal_tailored = {
        "contact": {"name": "Jane Doe"},
        "summary": "Engineer.",
        "skills": [],
        "experience": [],
        "education": [],
    }

    created = await app_client.post("/api/sessions", headers=_auth(victim_token))
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]

    hijack = await app_client.post(
        f"/api/sessions/{session_id}/tailored/commit",
        json={"tailored_output": minimal_tailored},
        headers=_auth(attacker_token),
    )
    assert hijack.status_code == 403, (
        "commit_tailored must reject a bearer that does not match the "
        f"claimed session, got {hijack.status_code} {hijack.text[:300]}"
    )


@pytest_asyncio.fixture()
async def superseded_token(
    app_client: AsyncClient, stub_turnstile: None
) -> tuple[str, str]:
    """``(dead_token, live_token)`` for one user whose login was replaced.

    Registering then logging in again rotates the ``sid`` claim, which is
    how the app revokes a stolen access token before it expires: the
    victim signs in again (or resets their password) and the old token
    must stop working everywhere.
    """
    email = f"replaced-{uuid.uuid4().hex[:10]}@example.com"
    register = await app_client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": _PASSWORD,
            "display_name": "replaced",
            "accepted_tos_version": "2026-06",
            "marketing_opt_in": False,
            "turnstile_token": "test-turnstile-token",
        },
    )
    assert register.status_code == 201, register.text
    dead_token = register.json()["access_token"]

    login = await app_client.post(
        "/api/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert login.status_code == 200, login.text
    return dead_token, login.json()["access_token"]


@pytest.mark.integration
async def test_superseded_token_is_rejected_on_a_gated_route(
    app_client: AsyncClient, superseded_token: tuple[str, str]
) -> None:
    """Positive control for the session-scoped assertions below.

    If this ever stops returning 401 the rotation never happened and the
    tests that follow would pass vacuously.
    """
    dead_token, _ = superseded_token
    response = await app_client.get("/api/resumes", headers=_auth(dead_token))
    assert response.status_code == 401, response.text
    assert response.json()["detail"]["code"] == "session_replaced"


@pytest.mark.integration
async def test_superseded_token_cannot_drive_a_claimed_session(
    app_client: AsyncClient, superseded_token: tuple[str, str]
) -> None:
    """Revocation must reach the session-scoped routes too.

    ``resolve_bearer_user_id`` decodes the access token itself instead of
    depending on ``get_current_user``, so it used to miss the ``sid``
    check that every other gated route applies. A phase run charges the
    owner's credits and retrieves against ``session.user_id``'s corpus,
    so a token the owner had already revoked could still spend their
    balance and pull their résumé text into a response.
    """
    dead_token, live_token = superseded_token

    created = await app_client.post("/api/sessions", headers=_auth(live_token))
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]

    denied = await app_client.post(
        f"/api/sessions/{session_id}/phases/1/run",
        json={},
        headers=_auth(dead_token),
    )
    assert denied.status_code == 401, (
        "a superseded access token must not start a phase run, got "
        f"{denied.status_code} {denied.text[:300]}"
    )

    allowed = await app_client.post(
        f"/api/sessions/{session_id}/phases/1/run",
        json={},
        headers=_auth(live_token),
    )
    assert allowed.status_code == 202, (
        "the live token must still drive its own session, got "
        f"{allowed.status_code} {allowed.text[:300]}"
    )


@pytest.mark.integration
async def test_superseded_token_cannot_commit_into_the_owners_corpus(
    app_client: AsyncClient, superseded_token: tuple[str, str]
) -> None:
    """``commit_tailored`` writes the master résumé and the RAG corpus.

    It resolves the target user from the bearer, so a revoked token
    reaching it would let a stolen session keep editing the account's
    long-lived corpus rather than just the throwaway tailoring session.
    """
    dead_token, live_token = superseded_token

    created = await app_client.post("/api/sessions", headers=_auth(live_token))
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]

    denied = await app_client.post(
        f"/api/sessions/{session_id}/tailored/commit",
        json={
            "tailored_output": {
                "contact": {"name": "Jane Doe"},
                "summary": "Engineer.",
                "skills": [],
                "experience": [],
                "education": [],
            }
        },
        headers=_auth(dead_token),
    )
    assert denied.status_code == 401, (
        "a superseded access token must not commit a tailored résumé, got "
        f"{denied.status_code} {denied.text[:300]}"
    )


@pytest.mark.integration
async def test_superseded_token_does_not_claim_a_new_session(
    app_client: AsyncClient, superseded_token: tuple[str, str]
) -> None:
    """``POST /api/sessions`` is public, so it binds rather than rejects.

    A revoked token must leave the new session anonymous: binding it
    would attach the work — and later the corpus writes it unlocks — to
    an account the caller no longer holds a live login for.
    """
    dead_token, live_token = superseded_token

    created = await app_client.post("/api/sessions", headers=_auth(dead_token))
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]

    session = await get_session(session_id)
    assert session is not None
    assert session.user_id is None, (
        "a superseded token claimed the new session for its subject"
    )

    # The live token still claims it, so refusing to bind costs the real
    # owner nothing.
    claimed = await app_client.post(
        f"/api/sessions/{session_id}/phases/1/run",
        json={},
        headers=_auth(live_token),
    )
    assert claimed.status_code == 202, claimed.text


@pytest.mark.integration
async def test_session_ids_are_unguessable_uuid4_capabilities() -> None:
    """The anonymous flow's only protection is that ids cannot be guessed.

    Every ``/api/sessions/*`` entry in ``PUBLIC_ROUTES`` rests on this.
    A switch to a counter, timestamp or short token would silently turn
    the whole anonymous flow into an enumerable one, and no other test
    in this module would notice.
    """
    ids = set()
    for _ in range(5):
        session = await create_session()
        parsed = uuid.UUID(session.session_id)
        assert parsed.version == 4, (
            f"session ids must be uuid4, got version {parsed.version}"
        )
        ids.add(session.session_id)
        await update_session(session)
    assert len(ids) == 5, "session ids must be unique"
