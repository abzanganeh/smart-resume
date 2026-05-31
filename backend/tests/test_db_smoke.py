"""DB smoke integration tests.

These tests require a live PostgreSQL database (with the pgvector extension
available) and are gated behind the ``integration`` marker so they are skipped
in standard unit-test runs.

Run with a local database:

    docker compose up -d postgres
    cd backend
    DATABASE_URL=postgresql+asyncpg://smart_resume:password@localhost:5433/smart_resume \\
        uv run pytest tests/test_db_smoke.py -m integration -v
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _require_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping integration tests")
    return url


@pytest_asyncio.fixture()
async def session() -> AsyncSession:  # type: ignore[override]
    """Create a fresh async session for each test."""
    url = _require_db_url()
    engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_select_one(session: AsyncSession) -> None:
    """Basic connectivity check: SELECT 1 must return 1."""
    result = await session.execute(text("SELECT 1"))
    assert result.scalar() == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pgvector_extension_present(session: AsyncSession) -> None:
    """Confirm the pgvector extension was enabled by the 0001_base migration."""
    result = await session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    )
    row = result.scalar()
    assert row == "vector", (
        "pgvector extension is not present. "
        "Run: cd backend && uv run alembic upgrade head"
    )
