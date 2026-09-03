"""Integration tests for public resume checkup endpoint (M13 Step 42)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

_SAMPLE_JD = (
    "Backend Engineer — Python, FastAPI, PostgreSQL, Kubernetes. "
    "5+ years building scalable APIs."
)


@pytest.mark.asyncio
async def test_checkup_rejects_empty_resume(app_client: AsyncClient) -> None:
    resp = await app_client.post(
        "/api/checkup",
        data={
            "jd_text": _SAMPLE_JD,
            "resume_text": "   ",
        },
    )
    assert resp.status_code == 422
    assert "empty" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_checkup_rejects_short_jd(app_client: AsyncClient) -> None:
    resp = await app_client.post(
        "/api/checkup",
        data={
            "jd_text": "too short",
            "resume_text": "Jane Doe\nSoftware Engineer\nPython, FastAPI",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_checkup_rejects_corrupt_pdf_upload(app_client: AsyncClient) -> None:
    resp = await app_client.post(
        "/api/checkup",
        data={"jd_text": _SAMPLE_JD},
        files={
            "file": ("resume.pdf", b"not-a-valid-pdf", "application/pdf"),
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"].lower()
    assert "pdf" in detail
    assert "paste" in detail or "corrupt" in detail or "could not read" in detail


@pytest.mark.asyncio
async def test_checkup_does_not_require_auth(app_client: AsyncClient) -> None:
    """Anonymous callers reach validation — not 401."""
    resp = await app_client.post(
        "/api/checkup",
        data={
            "jd_text": _SAMPLE_JD,
            "resume_text": "",
        },
    )
    assert resp.status_code != 401
