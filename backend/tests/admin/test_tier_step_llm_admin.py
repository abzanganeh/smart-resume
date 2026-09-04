"""Admin API for per-plan_code step LLM pins."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.model_registry import resolve_model
from app.llm.step_pin_cache import clear_step_pins_for_tests
from app.llm.tier_step_pin_cache import clear_tier_step_pins_for_tests
from app.models.admin import AdminRole
from app.models.tier_step_llm_config import TierStepLLMConfig
from app.services.llm.step_config import seed_step_llm_configs_if_empty
from tests.admin.conftest import issue_admin_session, make_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BULK_PAYLOAD = {
    "plan_code": "monthly_pro",
    "steps": ["phase3_rewrite", "chat", "cover_letter"],
    "provider": "openai",
    "model_string": "gpt-4o-mini",
    "notes": "bulk pin test",
}


@pytest.fixture(autouse=True)
def _clear_pins() -> None:
    clear_step_pins_for_tests()
    clear_tier_step_pins_for_tests()
    yield
    clear_step_pins_for_tests()
    clear_tier_step_pins_for_tests()


async def _bulk_headers(
    db_session: AsyncSession,
    *,
    email: str,
    role: AdminRole = AdminRole.super_admin,
) -> tuple[str, dict[str, str]]:
    admin, _secret = await make_admin(db_session, email=email, role=role)
    await db_session.commit()
    return await issue_admin_session(admin.id)


async def test_admin_tier_step_llm_list_requires_auth(app_client: AsyncClient) -> None:
    resp = await app_client.get("/api/admin/llm/tier-steps?plan_code=free")
    assert resp.status_code == 401


async def test_admin_tier_step_llm_create_and_resolve(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await seed_step_llm_configs_if_empty(db_session)
    await db_session.commit()

    admin, _secret = await make_admin(
        db_session, email="tier-pin@example.com", role=AdminRole.super_admin
    )
    await db_session.commit()
    token, headers = await issue_admin_session(admin.id)

    resp = await app_client.post(
        "/api/admin/llm/tier-steps",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json={
            "plan_codes": ["monthly_pro", "free"],
            "step": "phase3_rewrite",
            "provider": "openai",
            "model_string": "gpt-4o-mini",
            "notes": "tier pin test",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["step_configs"]) == 2
    assert body["audit_log_id"]

    provider, model = resolve_model("phase3_rewrite", plan_code="monthly_pro")
    assert provider == "openai"
    assert model == "gpt-4o-mini"

    list_resp = await app_client.get(
        "/api/admin/llm/tier-steps?plan_code=monthly_pro",
        headers={**headers, "Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    rows = {row["step"]: row for row in list_resp.json()}
    assert rows["phase3_rewrite"]["source"] == "tier_pin"


async def test_admin_tier_step_llm_delete_clears_pin(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _secret = await make_admin(
        db_session, email="tier-del@example.com", role=AdminRole.super_admin
    )
    await db_session.commit()
    token, headers = await issue_admin_session(admin.id)

    create_resp = await app_client.post(
        "/api/admin/llm/tier-steps",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json={
            "plan_codes": ["free"],
            "step": "chat",
            "provider": "openai",
            "model_string": "gpt-4o-mini",
        },
    )
    assert create_resp.status_code == 201

    del_resp = await app_client.delete(
        "/api/admin/llm/tier-steps/free/chat",
        headers={**headers, "Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 200

    provider, model = resolve_model("chat", plan_code="free")
    from app.llm.model_registry import STEP_DEFAULTS

    assert (provider, model) == STEP_DEFAULTS["chat"]


async def test_admin_tier_step_llm_create_rejects_unpriced_model(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _secret = await make_admin(
        db_session, email="tier-unpriced@example.com", role=AdminRole.super_admin
    )
    await db_session.commit()
    token, headers = await issue_admin_session(admin.id)

    resp = await app_client.post(
        "/api/admin/llm/tier-steps",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json={
            "plan_codes": ["free"],
            "step": "chat",
            "provider": "openai",
            "model_string": "nonexistent-model-xyz",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unpriced_model"


async def test_admin_tier_step_llm_create_rejects_inherited_step(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _secret = await make_admin(
        db_session, email="tier-inherited@example.com", role=AdminRole.super_admin
    )
    await db_session.commit()
    token, headers = await issue_admin_session(admin.id)

    resp = await app_client.post(
        "/api/admin/llm/tier-steps",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json={
            "plan_codes": ["free"],
            "step": "phase3_truthfulness",
            "provider": "openai",
            "model_string": "gpt-4o-mini",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "inherited_client_step"


async def test_admin_tier_step_llm_create_rejects_global_only_step(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _secret = await make_admin(
        db_session, email="tier-global@example.com", role=AdminRole.super_admin
    )
    await db_session.commit()
    token, headers = await issue_admin_session(admin.id)

    resp = await app_client.post(
        "/api/admin/llm/tier-steps",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json={
            "plan_codes": ["free"],
            "step": "company_intel",
            "provider": "openai",
            "model_string": "gpt-4o-mini",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "global_only_step"


async def test_bulk_tier_step_requires_auth(app_client: AsyncClient) -> None:
    resp = await app_client.post("/api/admin/llm/tier-steps/bulk", json=BULK_PAYLOAD)
    assert resp.status_code == 401


async def test_bulk_tier_step_rbac_super_admin_only(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, headers = await _bulk_headers(
        db_session,
        email="bulk-rbac-admin@example.com",
        role=AdminRole.admin,
    )
    resp = await app_client.post(
        "/api/admin/llm/tier-steps/bulk",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json=BULK_PAYLOAD,
    )
    assert resp.status_code == 403


async def test_bulk_tier_step_happy_path(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await seed_step_llm_configs_if_empty(db_session)
    await db_session.commit()

    token, headers = await _bulk_headers(
        db_session, email="bulk-happy@example.com"
    )

    resp = await app_client.post(
        "/api/admin/llm/tier-steps/bulk",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json=BULK_PAYLOAD,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["step_configs"]) == 3
    assert body["audit_log_id"]

    for step in BULK_PAYLOAD["steps"]:
        provider, model = resolve_model(step, plan_code="monthly_pro")
        assert provider == "openai"
        assert model == "gpt-4o-mini"


async def test_bulk_tier_step_rejects_locked_step(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, headers = await _bulk_headers(
        db_session, email="bulk-locked@example.com"
    )

    resp = await app_client.post(
        "/api/admin/llm/tier-steps/bulk",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json={
            **BULK_PAYLOAD,
            "steps": ["company_intel"],
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "bulk_validation_failed"
    assert detail["errors"] == [
        {"step": "company_intel", "code": "global_only_step"},
    ]


async def test_bulk_tier_step_rejects_mixed_valid_and_locked(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.llm.model_registry import STEP_DEFAULTS
    from app.routers import admin_tier_llm

    upsert_calls = 0
    original = admin_tier_llm._upsert_tier_step_pin

    async def _counting_upsert(*args, **kwargs):
        nonlocal upsert_calls
        upsert_calls += 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(admin_tier_llm, "_upsert_tier_step_pin", _counting_upsert)

    token, headers = await _bulk_headers(
        db_session, email="bulk-mixed@example.com"
    )

    before_count = (
        await db_session.execute(
            select(func.count())
            .select_from(TierStepLLMConfig)
            .where(TierStepLLMConfig.is_active.is_(True))
        )
    ).scalar_one()

    resp = await app_client.post(
        "/api/admin/llm/tier-steps/bulk",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json={
            **BULK_PAYLOAD,
            "steps": ["phase3_rewrite", "company_intel", "phase3_truthfulness"],
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "bulk_validation_failed"
    error_codes = {(e["step"], e["code"]) for e in detail["errors"]}
    assert ("company_intel", "global_only_step") in error_codes
    assert ("phase3_truthfulness", "inherited_client_step") in error_codes
    assert upsert_calls == 0

    provider, model = resolve_model("phase3_rewrite", plan_code="monthly_pro")
    assert (provider, model) == STEP_DEFAULTS["phase3_rewrite"]

    after_count = (
        await db_session.execute(
            select(func.count())
            .select_from(TierStepLLMConfig)
            .where(TierStepLLMConfig.is_active.is_(True))
        )
    ).scalar_one()
    assert after_count == before_count


async def test_bulk_tier_step_rejects_unpriced_model(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.llm.model_registry import STEP_DEFAULTS
    from app.routers import admin_tier_llm

    upsert_calls = 0
    original = admin_tier_llm._upsert_tier_step_pin

    async def _counting_upsert(*args, **kwargs):
        nonlocal upsert_calls
        upsert_calls += 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(admin_tier_llm, "_upsert_tier_step_pin", _counting_upsert)

    token, headers = await _bulk_headers(
        db_session, email="bulk-unpriced@example.com"
    )

    resp = await app_client.post(
        "/api/admin/llm/tier-steps/bulk",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json={
            **BULK_PAYLOAD,
            "model_string": "nonexistent-model-xyz",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unpriced_model"
    assert upsert_calls == 0

    provider, model = resolve_model("phase3_rewrite", plan_code="monthly_pro")
    assert (provider, model) == STEP_DEFAULTS["phase3_rewrite"]


async def test_bulk_tier_step_rejects_duplicate_steps(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, headers = await _bulk_headers(
        db_session, email="bulk-dup@example.com"
    )

    resp = await app_client.post(
        "/api/admin/llm/tier-steps/bulk",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json={
            **BULK_PAYLOAD,
            "steps": ["phase3_rewrite", "chat", "phase3_rewrite"],
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "bulk_validation_failed"
    assert {"step": "phase3_rewrite", "code": "duplicate_step"} in detail["errors"]


async def test_bulk_tier_step_zero_write_on_validation_failure(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.llm.model_registry import STEP_DEFAULTS
    from app.routers import admin_tier_llm

    upsert_calls = 0
    original = admin_tier_llm._upsert_tier_step_pin

    async def _counting_upsert(*args, **kwargs):
        nonlocal upsert_calls
        upsert_calls += 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(admin_tier_llm, "_upsert_tier_step_pin", _counting_upsert)

    token, headers = await _bulk_headers(
        db_session, email="bulk-zero-write@example.com"
    )

    before_rows = list(
        (
            await db_session.execute(select(TierStepLLMConfig))
        ).scalars().all()
    )
    before_active = {str(r.id) for r in before_rows if r.is_active}

    resp = await app_client.post(
        "/api/admin/llm/tier-steps/bulk",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json={
            **BULK_PAYLOAD,
            "steps": ["phase3_rewrite", "company_intel"],
        },
    )
    assert resp.status_code == 400
    assert upsert_calls == 0

    provider, model = resolve_model("phase3_rewrite", plan_code="monthly_pro")
    assert (provider, model) == STEP_DEFAULTS["phase3_rewrite"]

    after_rows = list(
        (
            await db_session.execute(select(TierStepLLMConfig))
        ).scalars().all()
    )
    after_active = {str(r.id) for r in after_rows if r.is_active}
    assert after_active == before_active
    assert len(after_rows) == len(before_rows)


async def test_bulk_tier_step_cache_refresh(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await seed_step_llm_configs_if_empty(db_session)
    await db_session.commit()

    token, headers = await _bulk_headers(
        db_session, email="bulk-cache@example.com"
    )

    resp = await app_client.post(
        "/api/admin/llm/tier-steps/bulk",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json={
            "plan_code": "free",
            "steps": ["polish", "story"],
            "provider": "openai",
            "model_string": "gpt-4o-mini",
        },
    )
    assert resp.status_code == 201, resp.text

    for step in ("polish", "story"):
        provider, model = resolve_model(step, plan_code="free")
        assert provider == "openai"
        assert model == "gpt-4o-mini"
