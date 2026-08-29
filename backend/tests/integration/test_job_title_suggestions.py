"""Integration tests for preferred job titles and corpus search access."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jobs import JobCache
from app.models.master_resume import MasterResume
from app.services.jobs.preferred_titles import set_preferred_titles
from tests.integration.test_auth import REGISTER_PAYLOAD
from tests.conftest import verify_user_email

pytestmark = pytest.mark.integration


async def _register(client: AsyncClient, db_session: AsyncSession) -> tuple[str, str]:
    email = f"titles-{uuid.uuid4().hex[:8]}@example.com"
    payload = {**REGISTER_PAYLOAD, "email": email}
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    user_id = body["user"]["id"]
    await verify_user_email(db_session, uuid.UUID(user_id))
    return body["access_token"], user_id


async def _seed_master_resume(db_session: AsyncSession, user_id: str) -> None:
    row = MasterResume(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_id),
        raw_text="Mobile Developer at ShelfMark. React Native app with 500 users.",
        parsed_sections={
            "experience": [{"title": "Mobile Developer", "company": "ShelfMark"}]
        },
        chunk_count=1,
    )
    db_session.add(row)
    await db_session.flush()


async def _seed_corpus_job(db_session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    row = JobCache(
        id=uuid.uuid4(),
        sources=["corpus"],
        external_ids={"greenhouse": "1"},
        title="Mobile Developer",
        company="Stripe",
        company_normalized="stripe",
        location="Remote",
        remote=True,
        employment_type="full-time",
        posted_date=now,
        description="React Native mobile developer role.",
        apply_url="https://boards.greenhouse.io/stripe/jobs/1",
        raw_json={},
        cached_at=now,
        expires_at=now + timedelta(days=7),
        dedup_key="url:https://boards.greenhouse.io/stripe/jobs/1",
        first_seen_at=now,
        last_seen_at=now,
        is_active=True,
        apply_url_normalized="https://boards.greenhouse.io/stripe/jobs/1",
        ats_type="greenhouse",
        external_job_id="1",
    )
    db_session.add(row)
    await db_session.flush()


@pytest.mark.asyncio
async def test_title_suggestions_require_master_resume(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    token, _ = await _register(app_client, db_session)
    r = await app_client.get(
        "/api/jobs/title-suggestions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_title_suggestions_from_resume(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client, db_session)
    await _seed_master_resume(db_session, user_id)
    await db_session.commit()

    r = await app_client.get(
        "/api/jobs/title-suggestions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["suggestions"]) == 10
    assert "Mobile Developer" in body["held_titles"]
    first = body["suggestions"][0]
    assert "title" in first
    assert "fit_score" in first
    assert isinstance(first["fit_score"], int)
    assert first["strengths"]
    assert body["suggestions"] == sorted(
        body["suggestions"], key=lambda row: row["fit_score"], reverse=True
    )


@pytest.mark.asyncio
async def test_put_preferred_titles_persists_source_hash(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """PUT /api/jobs/preferred-titles snapshots the master resume hash so that
    the next GET /preferences correctly reports stale=false immediately after."""
    token, user_id = await _register(app_client, db_session)
    await _seed_master_resume(db_session, user_id)
    await db_session.commit()

    r = await app_client.put(
        "/api/jobs/preferred-titles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "titles": [
                "Mobile Developer",
                "React Native Developer",
                "Software Engineer",
                "iOS Developer",
                "Android Developer",
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["confirmed"] is True
    assert r.json()["stale"] is False

    prefs = await app_client.get(
        "/api/jobs/preferences", headers={"Authorization": f"Bearer {token}"}
    )
    assert prefs.status_code == 200
    body = prefs.json()
    assert body["preferred_titles_confirmed"] is True
    assert body["preferred_titles_stale"] is False


@pytest.mark.asyncio
async def test_preferences_stale_after_master_resume_change(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """When the master resume text changes, /preferences must report stale=true."""
    token, user_id = await _register(app_client, db_session)
    await _seed_master_resume(db_session, user_id)
    await db_session.commit()

    r = await app_client.put(
        "/api/jobs/preferred-titles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "titles": [
                "Mobile Developer",
                "React Native Developer",
                "Software Engineer",
                "iOS Developer",
                "Android Developer",
            ]
        },
    )
    assert r.status_code == 200

    from sqlalchemy import select
    from app.models.master_resume import MasterResume

    resume = (
        await db_session.execute(
            select(MasterResume).where(MasterResume.user_id == uuid.UUID(user_id))
        )
    ).scalar_one()
    resume.raw_text = (
        "Now a Senior Backend Engineer at Stripe leading a distributed systems team. "
        "This is a substantive resume rewrite that must invalidate old suggestions."
    )
    await db_session.commit()

    prefs = await app_client.get(
        "/api/jobs/preferences", headers={"Authorization": f"Bearer {token}"}
    )
    assert prefs.status_code == 200
    body = prefs.json()
    assert body["preferred_titles_confirmed"] is True
    assert body["preferred_titles_stale"] is True


@pytest.mark.asyncio
async def test_put_preferences_cannot_overwrite_reserved_metadata(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Reserved keys in ``default_filters`` must be dropped, not merged."""
    token, user_id = await _register(app_client, db_session)
    await _seed_master_resume(db_session, user_id)
    await db_session.commit()

    # First set legitimate preferred titles so hash + confirmed metadata exist.
    r = await app_client.put(
        "/api/jobs/preferred-titles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "titles": [
                "Mobile Developer",
                "React Native Developer",
                "Software Engineer",
                "iOS Developer",
                "Android Developer",
            ]
        },
    )
    assert r.status_code == 200

    # Now attempt to poison the reserved keys via default_filters.
    attack = await app_client.put(
        "/api/jobs/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "default_filters": {
                "preferred_titles": ["Attacker Injected Title"],
                "preferred_titles_confirmed_at": "1970-01-01T00:00:00Z",
                "preferred_titles_source_hash": "poisoned",
                "remote": True,
            }
        },
    )
    assert attack.status_code == 200
    body = attack.json()
    assert "Attacker Injected Title" not in body["preferred_titles"]
    assert body["preferred_titles_confirmed"] is True
    assert body["preferred_titles_stale"] is False
    assert body["default_filters"].get("remote") is True


@pytest.mark.asyncio
async def test_put_preferred_titles_accepts_twelve_titles(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client, db_session)
    await _seed_master_resume(db_session, user_id)
    await db_session.commit()

    titles = [f"Role {i}" for i in range(12)]
    r = await app_client.put(
        "/api/jobs/preferred-titles",
        headers={"Authorization": f"Bearer {token}"},
        json={"titles": titles},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["titles"]) == 12
    assert body["confirmed"] is True
    assert body["max_allowed"] == 12


@pytest.mark.asyncio
async def test_free_user_corpus_search_after_preferred_titles(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, user_id = await _register(app_client, db_session)
    await _seed_master_resume(db_session, user_id)
    await _seed_corpus_job(db_session)

    from app.models.user import User
    from sqlalchemy import select

    user = (
        await db_session.execute(select(User).where(User.id == uuid.UUID(user_id)))
    ).scalar_one()
    set_preferred_titles(
        user,
        ["Mobile Developer"],
    )
    await db_session.commit()

    with (
        patch(
            "app.services.jobs.hirebase_client.search",
            new_callable=AsyncMock,
        ) as mock_search,
        patch(
            "app.services.jobs.job_service.settings.JOB_SEARCH_DB_MIN_RESULTS",
            1,
        ),
    ):
        r = await app_client.post(
            "/api/jobs/search",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "Mobile Developer", "page": 1, "page_size": 20},
        )
        mock_search.assert_not_called()

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    assert body["source"] == "corpus"
