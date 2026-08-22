"""RAG tenant isolation and right-to-erasure regressions.

Threat model
------------

``retrieve_for_jd`` is the only path that pulls stored user text into an
LLM prompt.  Two failure modes are catastrophic:

- **OWASP LLM09 / A01 (broken access control)** — a missing or wrong
  ``user_id`` predicate on any of the retrieval queries leaks one
  tenant's resume text into another tenant's generated resume, cover
  letter, or fit analysis.  There is no UI affordance that would surface
  this: the victim never sees it and the attacker sees plausible resume
  prose.
- **OWASP LLM09 / GDPR Art. 17** — account closure that leaves embedded
  chunks behind means deleted users keep influencing retrieval forever.

Every test below tags one tenant's chunk content with a unique secret
marker and asserts the marker never crosses the tenant boundary.  The
JD text is deliberately made byte-identical to the *other* tenant's
chunk, so with the deterministic embedder that chunk scores ~1.0 and
would rank first if the scoping predicate ever regressed.  A weak JD
would let a real leak hide below the similarity threshold.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_resume import MasterResumeChunk
from app.models.user import User
from app.models.user_corpus import CorpusSource, UserCorpusChunk
from app.services.export.closure import execute_closure
from app.services.master_resume.embedding import embed_text
from app.services.retrieval.retrieval_service import (
    RetrievalResult,
    _query_section,
    _query_user_corpus,
    retrieve_for_jd,
)
from tests.retrieval._helpers import (
    chunk,
    create_test_user,
    seed_master_resume_with_chunks,
)
from tests.security.conftest import secret_marker, seed_corpus_chunk

pytestmark = pytest.mark.integration


# Tenant A's own corpus shares no vocabulary with tenant B's, so a
# B-flavoured JD cannot accidentally match an A chunk and mask a leak.
_A_EXPERIENCE = "Ceramics studio manager glazing kiln firing schedules."
_A_EDUCATION = "BFA Ceramics 2014 Rhode Island."


def _all_returned_text(result: RetrievalResult) -> str:
    """Every chunk body the caller can observe, selected or skipped.

    ``skipped_chunks`` carries full ``content`` into the trace that the
    dashboard renders, so a leak there is just as real as one in
    ``selected_chunks``.
    """
    return "\n".join(
        [s.content for s in result.selected] + [s.content for s in result.skipped]
    )


def _returned_chunk_ids(result: RetrievalResult) -> set[str]:
    return {s.chunk_id for s in result.selected} | {
        s.chunk_id for s in result.skipped
    }


async def _chunk_ids_for(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    rows = (
        await db.execute(
            select(MasterResumeChunk.id).where(MasterResumeChunk.user_id == user_id)
        )
    ).scalars().all()
    return {str(r) for r in rows}


async def _count_master_chunks(db: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(MasterResumeChunk)
                .where(MasterResumeChunk.user_id == user_id)
            )
        ).scalar_one()
    )


async def _count_corpus_chunks(db: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(UserCorpusChunk)
                .where(UserCorpusChunk.user_id == user_id)
            )
        ).scalar_one()
    )


# ---------------------------------------------------------------------------
# master_resume_chunks isolation (LLM09 / A01)
# ---------------------------------------------------------------------------


async def test_retrieval_never_returns_another_users_master_resume_chunk(
    db_session: AsyncSession,
) -> None:
    marker_b = secret_marker("B")
    victim_text = (
        f"Directed the {marker_b} acquisition of Helio Robotics for 240 million."
    )

    user_a = await create_test_user(db_session, email="iso-a@example.com")
    user_b = await create_test_user(db_session, email="iso-b@example.com")

    await seed_master_resume_with_chunks(
        db_session,
        user_id=user_a.id,
        chunks=[
            chunk("experience", _A_EXPERIENCE),
            chunk("education", _A_EDUCATION),
        ],
    )
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user_b.id,
        chunks=[
            chunk("experience", victim_text),
            chunk("skills", f"{marker_b} mergers acquisitions diligence"),
        ],
    )

    # JD == B's chunk verbatim: cosine ~1.0 if the scoping filter fails.
    result = await retrieve_for_jd(
        db_session, user_id=user_a.id, jd_text=victim_text
    )

    assert marker_b not in _all_returned_text(result)
    b_ids = await _chunk_ids_for(db_session, user_b.id)
    assert b_ids, "tenant B fixture did not persist — test would pass vacuously"
    assert _returned_chunk_ids(result) & b_ids == set()


async def test_victim_can_retrieve_own_marked_chunk(
    db_session: AsyncSession,
) -> None:
    """Positive control for the isolation assertions above.

    Proves the marked chunk is retrievable at all, so a passing
    isolation test means "correctly scoped" rather than "the fixture
    never made it into the index".
    """
    marker_b = secret_marker("B")
    victim_text = f"Directed the {marker_b} acquisition of Helio Robotics."

    user_b = await create_test_user(db_session, email="iso-own@example.com")
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user_b.id,
        chunks=[chunk("experience", victim_text)],
    )

    result = await retrieve_for_jd(
        db_session, user_id=user_b.id, jd_text=victim_text
    )
    assert marker_b in _all_returned_text(result)


async def test_user_with_empty_corpus_gets_no_chunks_from_other_tenants(
    db_session: AsyncSession,
) -> None:
    """A brand-new user must retrieve nothing, not someone else's resume."""
    marker_b = secret_marker("B")
    victim_text = f"Principal engineer {marker_b} on the payments ledger rewrite."

    user_a = await create_test_user(db_session, email="empty-a@example.com")
    user_b = await create_test_user(db_session, email="empty-b@example.com")
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user_b.id,
        chunks=[
            chunk("experience", victim_text),
            chunk("education", f"MS Computer Science {marker_b} 2016."),
        ],
    )

    result = await retrieve_for_jd(
        db_session, user_id=user_a.id, jd_text=victim_text
    )

    assert result.selected == []
    assert result.skipped == []
    assert marker_b not in _all_returned_text(result)

    # ``retrieve_for_jd`` short-circuits on ``has_any_live_chunk`` for an
    # empty user, so the assertions above would still hold if the ANN
    # query itself were unscoped.  Query the section directly to pin the
    # predicate that actually enforces the boundary.
    jd_vector = await embed_text(victim_text)
    for section in ("experience", "education"):
        assert (
            await _query_section(
                db_session,
                user_id=user_a.id,
                section=section,
                jd_vector=jd_vector,
                limit=10,
            )
            == []
        )


async def test_critical_section_fallback_stays_tenant_scoped(
    db_session: AsyncSession,
) -> None:
    """The relaxed-threshold rescue must not widen the tenant boundary.

    ``_select_for_section`` re-ranks ignoring the similarity threshold
    for critical sections.  That is exactly the branch where an
    unscoped "just give me the best chunks" query would be tempting, so
    it needs its own assertion.
    """
    marker_b = secret_marker("B")
    victim_text = f"Chief of staff {marker_b} reporting to the CEO at Northwind."

    user_a = await create_test_user(db_session, email="fb-a@example.com")
    user_b = await create_test_user(db_session, email="fb-b@example.com")

    # A's chunks share no tokens with the JD, so every A section falls
    # through to the fallback path.
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user_a.id,
        chunks=[
            chunk("experience", _A_EXPERIENCE),
            chunk("education", _A_EDUCATION),
        ],
    )
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user_b.id,
        chunks=[chunk("experience", victim_text)],
    )

    result = await retrieve_for_jd(
        db_session, user_id=user_a.id, jd_text=victim_text
    )

    assert result.meta["fallback_used"] is True, (
        "expected the fallback branch to run — otherwise this test does "
        "not cover it"
    )
    assert marker_b not in _all_returned_text(result)
    a_ids = await _chunk_ids_for(db_session, user_a.id)
    assert _returned_chunk_ids(result) <= a_ids


# ---------------------------------------------------------------------------
# user_corpus_chunks isolation (LLM09 / A01)
# ---------------------------------------------------------------------------


async def test_user_corpus_chunks_are_tenant_scoped(
    db_session: AsyncSession,
) -> None:
    """The second retrieval source needs the same predicate as the first.

    ``_query_user_corpus`` is a separate hand-written SQL statement, so
    it can regress independently of the per-section query.  We assert on
    the query directly rather than only on ``retrieve_for_jd`` output
    because a high-scoring corpus chunk currently never reaches
    ``selected_chunks`` (see the projection defect noted in
    ``test_high_scoring_corpus_chunk_never_reaches_output``), which would
    make an end-to-end-only assertion pass vacuously.
    """
    marker_b = secret_marker("BCORPUS")
    victim_note = f"Salary expectation {marker_b} is 310000 base plus equity."

    user_a = await create_test_user(db_session, email="corpus-a@example.com")
    user_b = await create_test_user(db_session, email="corpus-b@example.com")

    # A needs at least one live master-resume chunk, otherwise
    # ``retrieve_for_jd`` short-circuits before the corpus query and the
    # end-to-end assertion below would not exercise it.
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user_a.id,
        chunks=[chunk("experience", _A_EXPERIENCE)],
    )
    await seed_corpus_chunk(
        db_session,
        user_id=user_a.id,
        content="Prefers remote work in the Pacific timezone.",
    )
    await seed_corpus_chunk(
        db_session,
        user_id=user_b.id,
        content=victim_note,
        source=CorpusSource.user_note,
    )

    jd_vector = await embed_text(victim_note)

    # Positive control: B can reach its own note at ~1.0 similarity, so a
    # missing predicate would surface it for A too.
    own = await _query_user_corpus(
        db_session, user_id=user_b.id, jd_vector=jd_vector, limit=10
    )
    assert [c.content for c in own] == [victim_note]

    leaked = await _query_user_corpus(
        db_session, user_id=user_a.id, jd_vector=jd_vector, limit=10
    )
    assert marker_b not in "\n".join(c.content for c in leaked)

    result = await retrieve_for_jd(
        db_session, user_id=user_a.id, jd_text=victim_note
    )
    assert marker_b not in _all_returned_text(result)
    b_corpus_ids = {
        str(r)
        for r in (
            await db_session.execute(
                select(UserCorpusChunk.id).where(
                    UserCorpusChunk.user_id == user_b.id
                )
            )
        ).scalars().all()
    }
    assert b_corpus_ids, "tenant B corpus fixture did not persist"
    assert _returned_chunk_ids(result) & b_corpus_ids == set()


@pytest.mark.xfail(
    reason=(
        "retrieve_for_jd step 6 projects selected_by_section over the "
        "_DEFAULT_SECTIONS tuple only, but corpus chunks are keyed by "
        "corpus_source (user_note, bullet_fix, tailored_resume, "
        "claimed_keyword).  A corpus chunk that passes the primary "
        "threshold is counted in retrieval_meta.corpus_chunks_added and "
        "charged against the token budget, then silently dropped before "
        "the prompt is rendered."
    ),
    strict=True,
)
async def test_high_scoring_corpus_chunk_never_reaches_output(
    db_session: AsyncSession,
) -> None:
    """Documents why the corpus test above asserts at the query layer.

    This is a correctness defect, not a leak — the pipeline fails closed.
    It matters here because it silently disarms any end-to-end assertion
    about corpus content, so the isolation test must not rely on one.
    """
    user = await create_test_user(db_session, email="corpus-proj@example.com")
    note = "Shipped the ledger rewrite and cut settlement latency in half."
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user.id,
        chunks=[chunk("experience", _A_EXPERIENCE)],
    )
    await seed_corpus_chunk(db_session, user_id=user.id, content=note)

    result = await retrieve_for_jd(db_session, user_id=user.id, jd_text=note)

    assert result.meta["corpus_chunks_added"] == 1
    assert note in "\n".join(s.content for s in result.selected)


# ---------------------------------------------------------------------------
# Right to erasure (LLM09 / GDPR Art. 17)
# ---------------------------------------------------------------------------


def _closure_side_effect_patches():
    """Patch the S3 and email side effects ``execute_closure`` performs."""
    return (
        patch("app.services.export.closure.delete_attachment"),
        patch("app.services.export.closure.delete_user_export_prefix"),
        patch("app.services.export.storage.delete_export_object"),
        patch(
            "app.services.auth.email.send_account_deleted_email",
            new=AsyncMock(return_value={"sent": False}),
        ),
    )


async def _run_closure(db_session: AsyncSession, user_id: uuid.UUID) -> bool:
    p1, p2, p3, p4 = _closure_side_effect_patches()
    with p1, p2, p3, p4:
        deleted = await execute_closure(db_session, user_id=user_id)
    await db_session.flush()
    return deleted


async def test_execute_closure_hard_deletes_master_resume_chunks(
    db_session: AsyncSession,
) -> None:
    """Erasure must remove the embeddings, not just the account row.

    A surviving ``master_resume_chunks`` row keeps feeding retrieval,
    which is both a GDPR Art. 17 violation and an LLM09 exposure.
    """
    marker = secret_marker("CLOSED")
    user = await create_test_user(db_session, email="closure-a@example.com")
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user.id,
        chunks=[
            chunk("experience", f"Staff engineer {marker} at Northwind Systems."),
            chunk("education", f"BS Physics {marker} 2011."),
        ],
    )
    assert await _count_master_chunks(db_session, user.id) == 2

    assert await _run_closure(db_session, user.id) is True

    assert await _count_master_chunks(db_session, user.id) == 0
    assert (
        await db_session.execute(select(User).where(User.id == user.id))
    ).scalar_one_or_none() is None


async def test_execute_closure_hard_deletes_user_corpus_chunks(
    db_session: AsyncSession,
) -> None:
    marker = secret_marker("CLOSEDCORPUS")
    user = await create_test_user(db_session, email="closure-corpus@example.com")
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user.id,
        chunks=[chunk("experience", f"Staff engineer {marker}.")],
    )
    await seed_corpus_chunk(
        db_session,
        user_id=user.id,
        content=f"Accepted bullet {marker} shipped the ledger rewrite.",
        source=CorpusSource.bullet_fix,
        section_type="experience",
    )
    assert await _count_corpus_chunks(db_session, user.id) == 1

    assert await _run_closure(db_session, user.id) is True

    assert await _count_corpus_chunks(db_session, user.id) == 0


async def test_execute_closure_leaves_other_tenants_chunks_intact(
    db_session: AsyncSession,
) -> None:
    """Erasure must be scoped too — a broad DELETE is its own incident."""
    user_a = await create_test_user(db_session, email="closure-scope-a@example.com")
    user_b = await create_test_user(db_session, email="closure-scope-b@example.com")
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user_a.id,
        chunks=[chunk("experience", "Closing account holder experience.")],
    )
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user_b.id,
        chunks=[chunk("experience", "Surviving account holder experience.")],
    )
    await seed_corpus_chunk(
        db_session,
        user_id=user_b.id,
        content="Surviving account holder note.",
    )

    assert await _run_closure(db_session, user_a.id) is True

    assert await _count_master_chunks(db_session, user_a.id) == 0
    assert await _count_master_chunks(db_session, user_b.id) == 1
    assert await _count_corpus_chunks(db_session, user_b.id) == 1


async def test_retrieval_returns_nothing_after_closure(
    db_session: AsyncSession,
) -> None:
    """End-to-end: a closed account's text is unreachable via retrieval."""
    marker = secret_marker("ERASED")
    victim_text = f"Led the {marker} platform migration at Northwind Systems."

    user_a = await create_test_user(db_session, email="erased-a@example.com")
    user_b = await create_test_user(db_session, email="erased-b@example.com")
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user_a.id,
        chunks=[
            chunk("experience", _A_EXPERIENCE),
            chunk("education", _A_EDUCATION),
        ],
    )
    await seed_master_resume_with_chunks(
        db_session,
        user_id=user_b.id,
        chunks=[chunk("experience", victim_text)],
    )

    assert await _run_closure(db_session, user_b.id) is True

    result = await retrieve_for_jd(
        db_session, user_id=user_a.id, jd_text=victim_text
    )
    assert marker not in _all_returned_text(result)
