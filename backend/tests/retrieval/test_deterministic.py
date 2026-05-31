"""Determinism: two retrieval calls with the same JD return identical traces.

IMPLEMENTATION_PLAN §6a explicitly requires byte-identical
``selected_chunks`` ordering across replays — this is what makes
phase-3 snapshots replayable and what makes the deterministic
ordering ``(score DESC, created_at ASC, id ASC)`` non-negotiable.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval.retrieval_service import retrieve_for_jd
from tests.retrieval._helpers import (
    chunk,
    create_test_user,
    seed_master_resume_with_chunks,
)

pytestmark = pytest.mark.integration


JD_TEXT = (
    "Senior Python backend engineer. Must have FastAPI, PostgreSQL, "
    "Kubernetes, and async patterns. Bonus: pgvector and LLM RAG."
)


# The chunk pool intentionally mixes high-relevance and low-relevance
# rows so the algorithm has to make selection + cap decisions.
def _seed_chunks():
    return [
        chunk(
            "experience",
            "Built FastAPI services in Python with PostgreSQL and pgvector.",
        ),
        chunk(
            "experience",
            "Led Kubernetes migration; rolled out async Python workers.",
        ),
        chunk(
            "experience",
            "Maintained a legacy Java monolith for invoice processing.",
        ),
        chunk(
            "project",
            "RAG pipeline with pgvector, LLM embeddings, and Python.",
        ),
        chunk(
            "skills",
            "Python FastAPI PostgreSQL Kubernetes async",
        ),
        chunk(
            "education",
            "BS Computer Science 2017; coursework in distributed systems.",
        ),
    ]


async def test_byte_identical_ordering_across_calls(
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    await seed_master_resume_with_chunks(
        db_session, user_id=user.id, chunks=_seed_chunks()
    )

    first = await retrieve_for_jd(db_session, user_id=user.id, jd_text=JD_TEXT)
    second = await retrieve_for_jd(db_session, user_id=user.id, jd_text=JD_TEXT)

    # Same selected order, including ``chunk_id`` UUID strings — proves
    # the tie-breaker ``(created_at ASC, id ASC)`` is in play.
    assert [s.chunk_id for s in first.selected] == [
        s.chunk_id for s in second.selected
    ]
    # Float scores must round-trip too so trace bytes match.
    assert [round(s.score, 6) for s in first.selected] == [
        round(s.score, 6) for s in second.selected
    ]
    # Top-level meta payload identical (embedding model, threshold, etc.).
    assert first.meta == second.meta

    # Trace JSON bytes are stable.  The frontend serialises this exact
    # shape into snapshot rows.
    assert json.dumps(first.to_trace(), sort_keys=True) == json.dumps(
        second.to_trace(), sort_keys=True
    )


async def test_top_scoring_chunks_come_first_per_section(
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    await seed_master_resume_with_chunks(
        db_session, user_id=user.id, chunks=_seed_chunks()
    )

    result = await retrieve_for_jd(db_session, user_id=user.id, jd_text=JD_TEXT)

    by_section: dict[str, list[float]] = {}
    for s in result.selected:
        by_section.setdefault(s.section, []).append(s.score)
    for section, scores in by_section.items():
        assert scores == sorted(scores, reverse=True), (
            f"section {section!r} scores not in descending order: {scores}"
        )


async def test_retrieval_meta_records_embedding_model(
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    await seed_master_resume_with_chunks(
        db_session, user_id=user.id, chunks=_seed_chunks()
    )

    result = await retrieve_for_jd(db_session, user_id=user.id, jd_text=JD_TEXT)
    assert result.meta["embedding_model"] == "text-embedding-3-small"
    assert "threshold_used" in result.meta
    assert "token_budget" in result.meta
