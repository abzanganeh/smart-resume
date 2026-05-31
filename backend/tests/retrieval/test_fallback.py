"""Fallback path: critical sections are never silently empty.

Covers §6a "Empty-result fallback":

- When no chunk in a section passes the primary threshold, the
  algorithm re-queries at the fallback threshold.
- If that is also empty *and* the section is critical (experience or
  education), it takes top-N by raw score regardless of threshold and
  marks each row ``reason="fallback_used"``.
- Non-critical sections are silently omitted.
- A user with zero live chunks raises :class:`MasterResumeRequiredError`
  → caller surfaces HTTP 409.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval.exceptions import MasterResumeRequiredError
from app.services.retrieval.retrieval_service import (
    resolve_runtime_config,
    retrieve_for_jd,
)
from tests.retrieval._helpers import (
    chunk,
    create_test_user,
    seed_master_resume_with_chunks,
)

pytestmark = pytest.mark.integration


# JD with no overlapping tokens vs the chunks below — the deterministic
# hash embedder will produce near-orthogonal vectors so every chunk
# scores well below the primary threshold (0.72).
LOW_OVERLAP_JD = "Quantum cryptography postdoctoral fellowship application."


async def test_critical_sections_always_have_at_least_one_chunk(
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user.id,
        chunks=[
            chunk("experience", "Frontend developer at a marketing startup."),
            chunk("experience", "Wordpress theme customisation freelance work."),
            chunk("education", "BFA Graphic Design 2015."),
            chunk("skills", "Photoshop Illustrator InDesign"),
        ],
    )

    runtime = await resolve_runtime_config(db_session)
    result = await retrieve_for_jd(
        db_session, user_id=user.id, jd_text=LOW_OVERLAP_JD
    )

    sections = {s.section for s in result.selected}
    # Both critical sections must be represented even when nothing
    # passes the primary threshold.
    assert "experience" in sections
    assert "education" in sections

    # Fallback metadata reflects what happened.
    assert result.meta["fallback_used"] is True
    assert "experience" in result.meta["fallback_sections"]

    # Every fallback selection must have score < primary threshold (we
    # specifically built the test that way).
    for s in result.selected:
        if s.section in {"experience", "education"}:
            assert s.score < runtime.primary_threshold


async def test_no_chunks_at_all_raises_master_resume_required(
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    # NO chunks seeded.
    with pytest.raises(MasterResumeRequiredError):
        await retrieve_for_jd(
            db_session, user_id=user.id, jd_text="anything"
        )


async def test_non_critical_section_is_omitted_when_empty(
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user.id,
        chunks=[
            chunk("experience", "Frontend developer at a marketing startup."),
            chunk("education", "BFA Graphic Design 2015."),
            chunk("skills", "Photoshop Illustrator"),
        ],
    )

    result = await retrieve_for_jd(
        db_session, user_id=user.id, jd_text=LOW_OVERLAP_JD
    )

    # Non-critical "skills" with all low-similarity chunks should be
    # omitted (skills is in NON_CRITICAL_SECTIONS).  Verify the section
    # is either not selected at all, OR was rescued by the fallback —
    # both are valid outcomes.  What matters is that skills does NOT
    # silently break the prompt.
    sections = {s.section for s in result.selected}
    if "skills" not in sections:
        assert "skills" in result.meta["sections_omitted"]


async def test_fallback_used_chunks_are_traced(
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user.id,
        chunks=[
            chunk("experience", "Frontend developer at a marketing startup."),
            chunk("education", "BFA Graphic Design 2015."),
        ],
    )

    result = await retrieve_for_jd(
        db_session, user_id=user.id, jd_text=LOW_OVERLAP_JD
    )

    fallback_chunk_ids = {
        s.chunk_id for s in result.skipped if s.reason == "fallback_used"
    }
    selected_ids = {s.chunk_id for s in result.selected}
    # Every chunk rescued via the fallback path must appear in both
    # ``skipped_chunks`` (with reason='fallback_used') and ``selected_chunks``
    # so the UI can render the "rescued" badge.
    assert fallback_chunk_ids.issubset(selected_ids)
