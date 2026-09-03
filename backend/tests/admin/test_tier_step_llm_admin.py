"""Admin API for per-plan_code step LLM pins."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.model_registry import resolve_model
from app.llm.step_pin_cache import clear_step_pins_for_tests
from app.llm.tier_step_pin_cache import clear_tier_step_pins_for_tests
from app.models.admin import AdminRole
from app.services.llm.step_config import seed_step_llm_configs_if_empty
from tests.admin.conftest import issue_admin_session, make_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_pins() -> None:
    clear_step_pins_for_tests()
    clear_tier_step_pins_for_tests()
    yield
    clear_step_pins_for_tests()
    clear_tier_step_pins_for_tests()


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
