"""Fixtures for the security regression suite.

The RAG isolation tests need the same guarantees the retrieval suite
relies on:

- A live Postgres with the ``vector`` extension (provided by the
  top-level ``db_session`` fixture, which skips when ``DATABASE_URL``
  is unset).
- A *fake* embedder so no test hits the OpenAI API and so similarity
  scores are a pure function of the chunk text.  This matters for
  tenant-isolation assertions: we deliberately embed a JD that is
  byte-identical to another tenant's chunk, which would score ~1.0 and
  therefore rank first if the scoping filter ever regressed.

The embedder is imported from :mod:`tests.retrieval.fake_embedder` so
both suites share one implementation.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_resume import EMBEDDING_DIM
from app.models.user_corpus import CorpusSource, UserCorpusChunk
from app.services.master_resume.chunking import count_tokens
from app.services.master_resume.embedding import set_fake_embedder
from tests.retrieval.fake_embedder import deterministic_embed


@pytest.fixture(autouse=True)
def install_deterministic_embedder():
    """Auto-install the deterministic embedder for every security test."""
    set_fake_embedder(deterministic_embed)
    try:
        yield
    finally:
        set_fake_embedder(None)


def secret_marker(tenant: str) -> str:
    """Return a unique, greppable marker to tag one tenant's content.

    Any occurrence of tenant B's marker in tenant A's retrieval output is
    a cross-tenant data leak, regardless of which code path produced it.
    """
    return f"XSECRET-{tenant}-{uuid.uuid4().hex}"


async def seed_corpus_chunk(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    content: str,
    source: CorpusSource = CorpusSource.user_note,
    section_type: str | None = None,
) -> UserCorpusChunk:
    """Insert one embedded ``user_corpus_chunks`` row for ``user_id``."""
    vectors = deterministic_embed([content], None)
    row = UserCorpusChunk(
        id=uuid.uuid4(),
        user_id=user_id,
        session_id=None,
        corpus_source=source,
        section_type=section_type,
        content=content,
        token_count=count_tokens(content),
        embedding=vectors[0] if vectors else [0.0] * EMBEDDING_DIM,
        chunk_metadata={},
    )
    db.add(row)
    await db.flush()
    await db.commit()
    return row
