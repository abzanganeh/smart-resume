"""Shared pytest fixtures for the backend test suite.

Provides:

- ``db_session``: a transaction-rolled-back AsyncSession against the
  configured Postgres URL.  Skips automatically when ``DATABASE_URL``
  is not exported (CI sets it; local devs run ``docker compose up -d
  postgres`` first).

- ``app_client``: a httpx ``AsyncClient`` bound to the FastAPI app,
  with the ``get_db`` dependency overridden to share the same session
  as ``db_session`` so router-level writes are visible to assertions.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.limiter import limiter
from app.main import app
from app.services.auth import session as redis_session
from app.services.admin_auth import tokens as admin_tokens
from app.services.session_store import reset_redis_keys_for_tests
from app.db.engine import get_db


# slowapi assigns rate limits by IP — across many tests they would
# starve each other.  Disable the limiter for the entire test run.
limiter.enabled = False


def _require_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping DB-backed test")
    return url


@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession that is rolled back at the end of the test."""
    url = _require_db_url()
    engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        # Wipe identity + billing + admin tables so tests are isolated
        # regardless of run order.  RESTART IDENTITY CASCADE handles the
        # FK closure automatically.  ``admin_audit_log`` cannot be
        # truncated normally because the append-only trigger blocks
        # DELETE/UPDATE; TRUNCATE bypasses the trigger so we keep it
        # in the list.
        await session.execute(
            text(
                "TRUNCATE TABLE "
                "job_descriptions, "
                "saved_job, job_cache, job_search_log, saved_search, "
                "application_attachments, offer_details, interview_rounds, applications, "
                "ats_score_history, resume_records, "
                "fit_analyses, master_resume_chunks, master_resumes, "
                "web_push_subscriptions, notification_preferences, "
                "export_jobs, closure_requests, "
                "announcements, feature_flags, admin_invites, "
                "admin_audit_log, notifications, "
                "stripe_webhook_events, refund_records, "
                "credit_transactions, subscriptions, plan_configs, tier_limits_config, "
                "llm_configs, "
                "auth_audit_log, refresh_tokens, users, admin_users "
                "RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
        yield session
        await session.rollback()
    await engine.dispose()


@pytest_asyncio.fixture()
async def app_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """ASGI test client with ``get_db`` dependency overridden."""

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        # Use the same session as the test so writes are visible to
        # subsequent assertions.  Commit at the end of each request so
        # later requests see the writes.
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = _override_db
    redis_session._reset_for_tests()  # type: ignore[attr-defined]
    admin_tokens._reset_for_tests()
    await reset_redis_keys_for_tests()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(get_db, None)
    redis_session._reset_for_tests()  # type: ignore[attr-defined]
    admin_tokens._reset_for_tests()
    await reset_redis_keys_for_tests()
