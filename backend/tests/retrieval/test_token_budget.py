"""Token budget: chunks dropped when over budget; top-1 per section never dropped.

Covers §6a step 5 ("Enforce global token budget"):

- Drop lowest-scoring chunks across all sections until under budget.
- Never drop the top-1 chunk of a section that has any qualifying chunk.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval import config as cfg
from app.services.retrieval import retrieval_service
from app.services.retrieval.retrieval_service import (
    RuntimeRetrievalConfig,
    retrieve_for_jd,
)
from tests.retrieval._helpers import (
    chunk,
    create_test_user,
    seed_master_resume_with_chunks,
)

pytestmark = pytest.mark.integration


# JD overlaps heavily with the seeded chunks so we *don't* fall into
# the fallback path — token-budget enforcement only kicks in when the
# selected set is already non-trivial.
JD_TEXT = (
    "Python FastAPI PostgreSQL Kubernetes async pgvector embeddings "
    "microservices distributed systems"
)


def _seed_chunks():
    rows = []
    # Five experience bullets and three skills bullets, all relevant.
    for i, content in enumerate(
        [
            "Python FastAPI service for Kubernetes async pipelines",
            "PostgreSQL pgvector embeddings retrieval Python",
            "Distributed systems microservices FastAPI Kubernetes Python",
            "Async pipelines pgvector Python PostgreSQL embeddings",
            "Kubernetes Python FastAPI microservices",
        ]
    ):
        rows.append(chunk("experience", content))
    for i, content in enumerate(
        [
            "Python FastAPI",
            "Kubernetes PostgreSQL pgvector",
            "Async distributed systems embeddings",
        ]
    ):
        rows.append(chunk("skills", content))
    return rows


@pytest.fixture
def tight_budget(monkeypatch: pytest.MonkeyPatch):
    """Force a very small token budget so eviction is unavoidable."""
    original = retrieval_service.resolve_runtime_config

    async def fake_resolve(db):  # noqa: ARG001
        base = await original(db)
        return cast(
            RuntimeRetrievalConfig,
            replace(base, token_budget=8),  # 8 tokens is well below the seed total
        )

    monkeypatch.setattr(
        retrieval_service, "resolve_runtime_config", fake_resolve
    )


async def test_lowest_score_chunks_dropped_when_over_budget(
    db_session: AsyncSession, tight_budget
) -> None:
    user = await create_test_user(db_session)
    await seed_master_resume_with_chunks(
        db_session, user_id=user.id, chunks=_seed_chunks()
    )

    result = await retrieve_for_jd(
        db_session, user_id=user.id, jd_text=JD_TEXT
    )

    # Something must have been evicted (the seed adds way more than 8 tokens).
    evicted = [s for s in result.skipped if s.reason == "budget_exceeded"]
    assert evicted, "expected at least one chunk evicted by the budget pass"

    # All evictions must come from the lower-scoring tail, never the
    # top of any section.  We assert this by checking that, per section,
    # the *minimum* surviving score is >= the *maximum* evicted score.
    surviving_by_section: dict[str, list[float]] = {}
    for s in result.selected:
        surviving_by_section.setdefault(s.section, []).append(s.score)
    evicted_by_section: dict[str, list[float]] = {}
    for s in evicted:
        evicted_by_section.setdefault(s.section, []).append(s.score)
    for section, ev_scores in evicted_by_section.items():
        surv = surviving_by_section.get(section, [])
        if not surv:
            continue  # the whole section may have been pruned to top-1
        assert min(surv) >= max(ev_scores), (
            f"budget pass evicted higher-scoring rows than it kept in {section}"
        )


async def test_top_1_per_section_never_dropped(
    db_session: AsyncSession, tight_budget
) -> None:
    user = await create_test_user(db_session)
    await seed_master_resume_with_chunks(
        db_session, user_id=user.id, chunks=_seed_chunks()
    )

    result = await retrieve_for_jd(
        db_session, user_id=user.id, jd_text=JD_TEXT
    )

    selected_sections = {s.section for s in result.selected}
    # Every section that had qualifying chunks before the budget pass
    # must still have at least one selected (the top-1 pin).  We know
    # the seed has both experience and skills chunks that pass the
    # primary threshold against the JD.
    assert "experience" in selected_sections
    assert "skills" in selected_sections

    # The very top chunk per section must be retained.  We re-derive
    # "top" from the union of selected + budget-evicted in order.
    by_section: dict[str, list[tuple[float, str, str]]] = {}
    for s in result.selected:
        by_section.setdefault(s.section, []).append(("kept", s.score, s.chunk_id))
    for s in result.skipped:
        if s.reason == "budget_exceeded":
            by_section.setdefault(s.section, []).append(("dropped", s.score, s.chunk_id))

    for section, items in by_section.items():
        items.sort(key=lambda x: -x[1])  # highest score first
        # The single highest-scoring row in this section must not have
        # been dropped by the budget pass.
        top_state, _, top_id = items[0]
        kept_in_section = [
            s.chunk_id for s in result.selected if s.section == section
        ]
        assert top_id in kept_in_section, (
            f"section {section!r} top-1 chunk {top_id} was dropped by budget pass"
        )
        assert top_state == "kept"


async def test_within_budget_no_chunks_dropped(
    db_session: AsyncSession,
) -> None:
    """When the prompt fits comfortably, nothing is evicted by the budget pass."""
    user = await create_test_user(db_session)
    await seed_master_resume_with_chunks(
        db_session, user_id=user.id, chunks=_seed_chunks()
    )

    result = await retrieve_for_jd(
        db_session, user_id=user.id, jd_text=JD_TEXT
    )
    # Default token budget is 6000; the seed corpus is < 200 tokens.
    assert result.meta["token_budget"] == cfg.RETRIEVAL_TOKEN_BUDGET
    budget_skipped = [s for s in result.skipped if s.reason == "budget_exceeded"]
    assert budget_skipped == []
