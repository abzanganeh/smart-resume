"""Application label on tailoring sessions."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.session_store import get_session

pytestmark = pytest.mark.integration


async def test_patch_application_label_persists_on_session(
    app_client: AsyncClient,
) -> None:
    created = await app_client.post("/api/sessions")
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    r = await app_client.patch(
        f"/api/sessions/{session_id}/application",
        json={"display_name": "Acme Health — Senior Backend"},
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "Acme Health — Senior Backend"

    stored = await get_session(session_id)
    assert stored is not None
    assert stored.application_display_name == "Acme Health — Senior Backend"

    check = await app_client.get(f"/api/sessions/{session_id}")
    assert check.status_code == 200
    assert check.json()["application_display_name"] == "Acme Health — Senior Backend"
