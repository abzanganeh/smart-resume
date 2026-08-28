"""Admin API for per-step LLM pins."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.model_registry import resolve_model
from app.llm.step_pin_cache import clear_step_pins_for_tests
from app.models.admin import AdminRole
from app.services.llm.step_config import seed_step_llm_configs_if_empty
from tests.admin.conftest import issue_admin_session, make_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_pins() -> None:
    clear_step_pins_for_tests()
    yield
    clear_step_pins_for_tests()


async def test_admin_step_llm_list_requires_auth(app_client: AsyncClient) -> None:
    resp = await app_client.get("/api/admin/llm/steps")
    assert resp.status_code == 401


async def test_admin_step_llm_create_updates_resolve_model(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await seed_step_llm_configs_if_empty(db_session)
    await db_session.commit()

    admin, _secret = await make_admin(
        db_session, email="step-pin@example.com", role=AdminRole.super_admin
    )
    await db_session.commit()
    token, headers = await issue_admin_session(admin.id)

    resp = await app_client.post(
        "/api/admin/llm/steps",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json={
            "step": "checkup",
            "provider": "openai",
            "model_string": "gpt-4o-mini",
            "notes": "rbac test pin",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["step_config"]["step"] == "checkup"
    assert body["step_config"]["provider"] == "openai"
    assert body["audit_log_id"]

    provider, model = resolve_model("checkup")
    assert provider == "openai"
    assert model == "gpt-4o-mini"


async def test_admin_step_llm_create_rejects_unpriced_model(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, _secret = await make_admin(
        db_session, email="unpriced@example.com", role=AdminRole.super_admin
    )
    await db_session.commit()
    token, headers = await issue_admin_session(admin.id)

    resp = await app_client.post(
        "/api/admin/llm/steps",
        headers={**headers, "Authorization": f"Bearer {token}"},
        json={
            "step": "chat",
            "provider": "openai",
            "model_string": "nonexistent-model-xyz",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unpriced_model"
