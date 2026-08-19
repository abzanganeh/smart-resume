"""Integration tests for the tracker's per-plan limits, duplicate detection,
archive workflow, and funnel endpoint (B3, 2026-08-19)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tracker import Application
from app.services.billing.tier_limits_lookup import TierLimits
from tests.integration.test_auth import REGISTER_PAYLOAD

pytestmark = pytest.mark.integration


async def _register(client: AsyncClient) -> tuple[str, uuid.UUID]:
    payload = {
        **REGISTER_PAYLOAD,
        "email": f"limits-{uuid.uuid4().hex[:8]}@example.com",
    }
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    return body["access_token"], uuid.UUID(body["user"]["id"])


def _limits(
    *,
    plan_code: str = "free",
    tracker_active_limit: int | None = 10,
) -> TierLimits:
    return TierLimits(
        plan_code=plan_code,
        resumes_per_period=6,
        cover_letters_per_period=6,
        searches_per_period=5,
        fit_analyses_per_period=3,
        checkups_per_period=3,
        story_sessions=1,
        coached_sessions=1,
        whisper_enabled=False,
        whisper_uses_per_period=0,
        tracker_active_limit=tracker_active_limit,
        soft_cap_message=None,
    )


def _patch_limits(limits: TierLimits):
    return patch(
        "app.routers.tracker.get_active_tier_limits",
        new=AsyncMock(return_value=limits),
    )


async def _create_app(
    client: AsyncClient,
    token: str,
    *,
    title: str = "Backend Engineer",
    company: str = "Acme Corp",
    confirm_duplicate: bool = False,
) -> dict:
    body: dict = {"jd_title": title, "jd_company": company}
    if confirm_duplicate:
        body["confirm_add_duplicate"] = True
    r = await client.post(
        "/api/applications",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    return {"status": r.status_code, "body": r.json()}


# ---------------------------------------------------------------------------
# tracker_active_limit enforcement
# ---------------------------------------------------------------------------


async def test_create_returns_409_when_active_slots_full(
    app_client: AsyncClient,
) -> None:
    """Once the user has ``tracker_active_limit`` active rows, new creates
    return 409 with a ``tracker_limit_reached`` code and structured detail."""
    token, _uid = await _register(app_client)
    limits = _limits(tracker_active_limit=2)

    with _patch_limits(limits):
        for i in range(2):
            r = await _create_app(
                app_client, token, title=f"Role {i}", company=f"Co {i}"
            )
            assert r["status"] == 201, r

        blocked = await _create_app(
            app_client, token, title="Role X", company="Co X"
        )
    assert blocked["status"] == 409
    detail = blocked["body"]["detail"]
    assert detail["code"] == "tracker_limit_reached"
    assert detail["limit"] == 2
    assert detail["active_count"] == 2
    assert detail["resolution"] == "archive_or_upgrade"


async def test_archiving_frees_an_active_slot(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, uid = await _register(app_client)
    limits = _limits(tracker_active_limit=1)

    with _patch_limits(limits):
        first = await _create_app(app_client, token, title="A", company="X")
        assert first["status"] == 201
        first_id = first["body"]["id"]

        # Second create is blocked by the cap.
        second = await _create_app(app_client, token, title="B", company="Y")
        assert second["status"] == 409

        # Archive frees a slot; retry succeeds.
        r = await app_client.post(
            f"/api/applications/{first_id}/archive",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["archived_at"] is not None

        retry = await _create_app(app_client, token, title="B", company="Y")
    assert retry["status"] == 201, retry


async def test_unarchive_blocked_when_at_active_limit(
    app_client: AsyncClient,
) -> None:
    """Un-archiving an application must fail cleanly if it would push the
    user over their active-slot cap."""
    token, _uid = await _register(app_client)
    limits = _limits(tracker_active_limit=1)

    with _patch_limits(limits):
        first = await _create_app(app_client, token, title="A", company="X")
        first_id = first["body"]["id"]

        # Archive first row so we can create a second active row.
        await app_client.post(
            f"/api/applications/{first_id}/archive",
            headers={"Authorization": f"Bearer {token}"},
        )
        second = await _create_app(app_client, token, title="B", company="Y")
        assert second["status"] == 201

        # Unarchive first row: would give us 2 active rows > limit 1.
        r = await app_client.post(
            f"/api/applications/{first_id}/unarchive",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "tracker_limit_reached"


async def test_none_limit_never_blocks_create(app_client: AsyncClient) -> None:
    """When ``tracker_active_limit`` is ``None`` (pro / plus) the enforcement
    never trips."""
    token, _uid = await _register(app_client)
    limits = _limits(tracker_active_limit=None)

    with _patch_limits(limits):
        for i in range(5):
            r = await _create_app(
                app_client, token, title=f"Role {i}", company=f"Co {i}"
            )
            assert r["status"] == 201, i


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


async def test_duplicate_returns_409_with_existing_id(
    app_client: AsyncClient,
) -> None:
    token, _uid = await _register(app_client)
    limits = _limits(tracker_active_limit=None)

    with _patch_limits(limits):
        first = await _create_app(
            app_client, token, title="Software Engineer", company="Google Inc"
        )
        assert first["status"] == 201
        existing_id = first["body"]["id"]

        # Same normalized (title, company) -- capitalisation and punctuation vary.
        blocked = await _create_app(
            app_client, token, title="software engineer", company="google, inc."
        )
    assert blocked["status"] == 409
    detail = blocked["body"]["detail"]
    assert detail["code"] == "duplicate_application"
    assert detail["existing_id"] == existing_id
    assert detail["lookback_days"] == 30
    assert detail["resolution"] == "confirm_add_duplicate"


async def test_confirm_add_duplicate_overrides_check(
    app_client: AsyncClient,
) -> None:
    token, _uid = await _register(app_client)
    limits = _limits(tracker_active_limit=None)

    with _patch_limits(limits):
        first = await _create_app(
            app_client, token, title="PM", company="Stripe"
        )
        assert first["status"] == 201

        retry = await _create_app(
            app_client,
            token,
            title="PM",
            company="Stripe",
            confirm_duplicate=True,
        )
    assert retry["status"] == 201


async def test_dedupe_ignores_archived_original(
    app_client: AsyncClient,
) -> None:
    """Archiving the original clears it from the dedupe window."""
    token, _uid = await _register(app_client)
    limits = _limits(tracker_active_limit=None)

    with _patch_limits(limits):
        first = await _create_app(
            app_client, token, title="Data Analyst", company="Netflix"
        )
        assert first["status"] == 201
        first_id = first["body"]["id"]

        await app_client.post(
            f"/api/applications/{first_id}/archive",
            headers={"Authorization": f"Bearer {token}"},
        )
        # After archive the same title/company is no longer a duplicate.
        second = await _create_app(
            app_client, token, title="Data Analyst", company="Netflix"
        )
    assert second["status"] == 201


async def test_different_role_is_not_a_duplicate(
    app_client: AsyncClient,
) -> None:
    token, _uid = await _register(app_client)
    limits = _limits(tracker_active_limit=None)

    with _patch_limits(limits):
        a = await _create_app(app_client, token, title="Engineer", company="X")
        b = await _create_app(
            app_client, token, title="Senior Engineer", company="X"
        )
    assert a["status"] == 201
    assert b["status"] == 201


# ---------------------------------------------------------------------------
# Archive workflow + GET filtering
# ---------------------------------------------------------------------------


async def test_get_applications_default_hides_archived(
    app_client: AsyncClient,
) -> None:
    token, _uid = await _register(app_client)
    with _patch_limits(_limits(tracker_active_limit=None)):
        first = await _create_app(app_client, token, title="A", company="X")
        first_id = first["body"]["id"]
        await _create_app(app_client, token, title="B", company="Y")

        await app_client.post(
            f"/api/applications/{first_id}/archive",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Default: active only.
        r = await app_client.get(
            "/api/applications", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        active_ids = {row["id"] for row in r.json()}
        assert first_id not in active_ids

        # archived=true: only archived.
        r = await app_client.get(
            "/api/applications?archived=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        archived_ids = {row["id"] for row in r.json()}
        assert archived_ids == {first_id}

        # archived=all: both.
        r = await app_client.get(
            "/api/applications?archived=all",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert len(r.json()) == 2


async def test_archive_endpoint_idempotent(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    token, _uid = await _register(app_client)
    with _patch_limits(_limits(tracker_active_limit=None)):
        created = await _create_app(app_client, token, title="A", company="X")
        app_id = created["body"]["id"]

        first = await app_client.post(
            f"/api/applications/{app_id}/archive",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert first.status_code == 200
        first_ts = first.json()["archived_at"]

        second = await app_client.post(
            f"/api/applications/{app_id}/archive",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert second.status_code == 200
        assert second.json()["archived_at"] == first_ts


# ---------------------------------------------------------------------------
# Funnel endpoint
# ---------------------------------------------------------------------------


async def test_funnel_returns_grouped_counts_and_limits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, uid = await _register(app_client)
    limits = _limits(tracker_active_limit=25)

    with _patch_limits(limits):
        # 2 draft, 1 archived
        a = await _create_app(app_client, token, title="A", company="Co1")
        await _create_app(app_client, token, title="B", company="Co2")
        c = await _create_app(app_client, token, title="C", company="Co3")

        # Mark one as applied via PATCH.
        await app_client.patch(
            f"/api/applications/{a['body']['id']}",
            json={"status": "applied"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Archive one.
        await app_client.post(
            f"/api/applications/{c['body']['id']}/archive",
            headers={"Authorization": f"Bearer {token}"},
        )

        r = await app_client.get(
            "/api/applications/funnel",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200, r.text
    payload = r.json()
    counts = payload["status_counts"]
    assert counts["applied"] == 1
    assert counts["draft"] == 1
    assert payload["active_total"] == 2
    assert payload["archived_total"] == 1
    assert payload["total"] == 3
    assert payload["tracker_active_limit"] == 25


async def test_funnel_returns_zero_counts_for_new_user(
    app_client: AsyncClient,
) -> None:
    token, _uid = await _register(app_client)
    with _patch_limits(_limits(tracker_active_limit=10)):
        r = await app_client.get(
            "/api/applications/funnel",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    payload = r.json()
    assert payload["active_total"] == 0
    assert payload["archived_total"] == 0
    assert payload["total"] == 0
    assert all(v == 0 for v in payload["status_counts"].values())
    assert payload["tracker_active_limit"] == 10


async def test_funnel_scoped_to_user(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Two users' rows must not leak into each other's funnel counts."""
    limits = _limits(tracker_active_limit=None)
    with _patch_limits(limits):
        token1, _u1 = await _register(app_client)
        token2, _u2 = await _register(app_client)

        await _create_app(app_client, token1, title="A", company="X")
        await _create_app(app_client, token1, title="B", company="Y")
        await _create_app(app_client, token2, title="C", company="Z")

        r1 = await app_client.get(
            "/api/applications/funnel",
            headers={"Authorization": f"Bearer {token1}"},
        )
        r2 = await app_client.get(
            "/api/applications/funnel",
            headers={"Authorization": f"Bearer {token2}"},
        )
    assert r1.json()["total"] == 2
    assert r2.json()["total"] == 1
