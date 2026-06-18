"""Integration tests for GET /api/interview-questions."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_interview_questions_universal_only(app_client: AsyncClient) -> None:
    r = await app_client.get("/api/interview-questions", params={"limit": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 5
    assert len(body["questions"]) == 5
    assert all(q["domain"] == "universal" for q in body["questions"])
    assert body["questions"][0]["text"]


@pytest.mark.asyncio
async def test_interview_questions_domain_merge(app_client: AsyncClient) -> None:
    r = await app_client.get(
        "/api/interview-questions",
        params={"domain": "software_engineering", "limit": 40},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    domains = {q["domain"] for q in body["questions"]}
    assert "universal" in domains
    assert "software_engineering" in domains
    assert body["domain"] == "software_engineering"


@pytest.mark.asyncio
async def test_interview_questions_accepts_company_and_role(app_client: AsyncClient) -> None:
    r = await app_client.get(
        "/api/interview-questions",
        params={
            "domain": "software engineering",
            "company": "Acme Corp",
            "role": "Staff Engineer",
            "limit": 15,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["company"] == "Acme Corp"
    assert body["role"] == "Staff Engineer"
    assert body["total"] == 15
