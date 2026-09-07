"""Unit tests for local staging job_cache sample seed."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from scripts.seed_staging_job_cache import _SAMPLE_JOBS, seed_staging_job_cache

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_seed_staging_job_cache_upserts_each_sample() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__.return_value = session
    cm.__aexit__.return_value = None

    with (
        patch(
            "scripts.seed_staging_job_cache.async_session_factory",
            return_value=cm,
        ),
        patch(
            "scripts.seed_staging_job_cache.upsert_job_cache",
            new_callable=AsyncMock,
        ) as mock_upsert,
    ):
        count = await seed_staging_job_cache()

    assert count == len(_SAMPLE_JOBS)
    assert mock_upsert.await_count == len(_SAMPLE_JOBS)
    for call in mock_upsert.await_args_list:
        record = call.args[1]
        assert record.get("is_active") is True
        assert record["sources"] == ["corpus"]
    session.commit.assert_awaited_once()
