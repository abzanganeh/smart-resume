"""Integration tests for POST /api/profile/resume/from-story"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.master_resume.embedding import set_fake_embedder
from tests.retrieval.fake_embedder import deterministic_embed

pytestmark = pytest.mark.integration


REGISTER_PAYLOAD = {
    "email": "story-user@example.com",
    "password": "tr0ub4dor&3story-mode-test",
    "display_name": "Story User",
    "accepted_tos_version": "2026-06",
    "marketing_opt_in": False,
}

VALID_SEGMENTS = [
    "I worked at SecureAuth from 2022 to 2025 as a Senior Software Engineer "
    "building anomaly detection systems and ML pipelines for identity security "
    "across millions of daily authentications.",
    "Before that I was at Acceptto from 2016 to 2022 building behavioral "
    "authentication systems using Python, Kubernetes, and PostgreSQL for "
    "enterprise customers in financial services and healthcare.",
    "Earlier I led backend platform work focused on API design, observability, "
    "and mentoring engineers through design reviews and production incident response.",
]


@pytest.fixture(autouse=True)
def _install_fake_embedder():
    set_fake_embedder(deterministic_embed)
    try:
        yield
    finally:
        set_fake_embedder(None)


async def _register_and_login(client: AsyncClient) -> str:
    r = await client.post("/api/auth/register", json=REGISTER_PAYLOAD)
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_story_endpoint_happy_path(app_client: AsyncClient):
    """Valid segments → 200 with chunk_count > 0."""
    token = await _register_and_login(app_client)

    MOCK_DRAFT = (
        "PROFESSIONAL SUMMARY\nExperienced engineer with 9 years of Python.\n\n"
        "SKILLS\nPython, AWS, Kubernetes\n\n"
        "EXPERIENCE\nSecureAuth | Senior Engineer | 2022 – 2025\n• Built anomaly detection\n"
    )

    with patch("app.routers.profile.story_to_resume", new_callable=AsyncMock) as mock_s2r:
        mock_s2r.return_value = MOCK_DRAFT
        response = await app_client.post(
            "/api/profile/resume/from-story",
            json={"segments": VALID_SEGMENTS, "whisper_path": False},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["chunk_count"] > 0


@pytest.mark.asyncio
async def test_story_endpoint_too_few_words(app_client: AsyncClient):
    """Segments with fewer than 50 words total → 422."""
    token = await _register_and_login(app_client)
    response = await app_client.post(
        "/api/profile/resume/from-story",
        json={"segments": ["Hi", "I worked"], "whisper_path": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_story_endpoint_too_many_segments(app_client: AsyncClient):
    """31 segments → 422."""
    token = await _register_and_login(app_client)
    long_segment = "I worked at a company for many years and built important systems. " * 2
    segments = [long_segment] * 31
    response = await app_client.post(
        "/api/profile/resume/from-story",
        json={"segments": segments, "whisper_path": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_story_endpoint_llm_failure(app_client: AsyncClient):
    """LLM RuntimeError → 502 with story_conversion_failed code."""
    token = await _register_and_login(app_client)
    with patch("app.routers.profile.story_to_resume", side_effect=RuntimeError("LLM failed")):
        response = await app_client.post(
            "/api/profile/resume/from-story",
            json={"segments": VALID_SEGMENTS, "whisper_path": False},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "story_conversion_failed"


@pytest.mark.asyncio
async def test_story_endpoint_unauthenticated(app_client: AsyncClient):
    """No auth header → 401."""
    response = await app_client.post(
        "/api/profile/resume/from-story",
        json={"segments": ["Some career story text goes here."], "whisper_path": False},
    )
    assert response.status_code == 401
