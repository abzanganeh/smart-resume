"""Unit tests for the corpus_writer service.

All DB and embedding calls are mocked so the tests run without a live
Postgres instance.  The primary contract under test:

1. embed_tailored_resume extracts summary + experience bullets and
   calls _insert_chunks with the correct metadata shapes.
2. embed_bullet_fix passes a single fragment with section_type=experience.
3. embed_user_notes passes a single fragment with section_type=None.
4. embed_claimed_keywords passes one fragment per keyword.
5. Truncation: fragments longer than _MAX_FRAGMENT_CHARS are capped.
6. Graceful degradation: any exception inside embed_* is swallowed and
   logged as a warning, never re-raised to the caller.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.corpus_writer import (
    _MAX_FRAGMENT_CHARS,
    _truncate,
    embed_bullet_fix,
    embed_claimed_keywords,
    embed_tailored_resume,
    embed_user_notes,
)


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------


def test_truncate_short_string_unchanged():
    assert _truncate("hello") == "hello"


def test_truncate_strips_whitespace():
    assert _truncate("  hi  ") == "hi"


def test_truncate_caps_at_max():
    long = "x" * (_MAX_FRAGMENT_CHARS + 100)
    result = _truncate(long)
    assert len(result) == _MAX_FRAGMENT_CHARS


def test_truncate_empty_returns_empty():
    assert _truncate("") == ""
    assert _truncate("   ") == ""


# ---------------------------------------------------------------------------
# Helpers for mocking the full async DB pipeline
# ---------------------------------------------------------------------------


def _fake_tailored_output(summary: str = "Experienced engineer", experience=None):
    if experience is None:
        experience = [
            SimpleNamespace(
                company="Acme",
                title="SWE",
                bullets=["Built X", "Led Y"],
            )
        ]
    return SimpleNamespace(
        summary=summary,
        experience=experience,
        projects=[],
    )


def _make_db_ctx():
    """Return a mock async context manager that yields a mock db session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, db


# ---------------------------------------------------------------------------
# embed_tailored_resume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_tailored_resume_inserts_summary_and_bullets():
    user_id = uuid.uuid4()
    session_id = "sess-abc"
    output = _fake_tailored_output()

    ctx, db = _make_db_ctx()
    added: list = []
    db.add = lambda obj: added.append(obj)

    with (
        patch(
            "app.services.corpus_writer.async_session_factory",
            return_value=ctx,
        ),
        patch(
            "app.services.corpus_writer.embed_texts",
            new_callable=AsyncMock,
            return_value=[[0.1] * 1536 for _ in range(3)],
        ),
        patch(
            "app.services.corpus_writer._soft_delete_session_source",
            new_callable=AsyncMock,
        ),
    ):
        await embed_tailored_resume(
            user_id=user_id,
            session_id=session_id,
            tailored_output=output,
        )

    # Summary + 2 bullets = 3 chunks
    assert len(added) == 3
    section_types = {obj.section_type for obj in added}
    assert "summary" in section_types
    assert "experience" in section_types


@pytest.mark.asyncio
async def test_embed_tailored_resume_skips_empty_bullets():
    user_id = uuid.uuid4()
    session_id = "sess-abc"
    experience = [SimpleNamespace(company="X", title="Y", bullets=["", "  ", "Real bullet"])]
    output = _fake_tailored_output(summary="", experience=experience)

    ctx, db = _make_db_ctx()
    added: list = []
    db.add = lambda obj: added.append(obj)

    with (
        patch("app.services.corpus_writer.async_session_factory", return_value=ctx),
        patch(
            "app.services.corpus_writer.embed_texts",
            new_callable=AsyncMock,
            return_value=[[0.1] * 1536],
        ),
        patch(
            "app.services.corpus_writer._soft_delete_session_source",
            new_callable=AsyncMock,
        ),
    ):
        await embed_tailored_resume(
            user_id=user_id,
            session_id=session_id,
            tailored_output=output,
        )

    assert len(added) == 1
    assert added[0].content == "Real bullet"


@pytest.mark.asyncio
async def test_embed_tailored_resume_swallows_exception():
    """Corpus write failure must never raise to the caller."""
    with patch(
        "app.services.corpus_writer.async_session_factory",
        side_effect=RuntimeError("DB down"),
    ):
        # Should complete without raising.
        await embed_tailored_resume(
            user_id=uuid.uuid4(),
            session_id="s",
            tailored_output=_fake_tailored_output(),
        )


# ---------------------------------------------------------------------------
# embed_bullet_fix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_bullet_fix_correct_metadata():
    user_id = uuid.uuid4()
    ctx, db = _make_db_ctx()
    added: list = []
    db.add = lambda obj: added.append(obj)

    with (
        patch("app.services.corpus_writer.async_session_factory", return_value=ctx),
        patch(
            "app.services.corpus_writer.embed_texts",
            new_callable=AsyncMock,
            return_value=[[0.2] * 1536],
        ),
    ):
        await embed_bullet_fix(
            user_id=user_id,
            session_id="sess",
            bullet_text="Increased revenue by 40%",
            company="Contoso",
            bullet_index=2,
        )

    assert len(added) == 1
    chunk = added[0]
    assert chunk.section_type == "experience"
    assert chunk.chunk_metadata["company"] == "Contoso"
    assert chunk.chunk_metadata["bullet_index"] == 2


@pytest.mark.asyncio
async def test_embed_bullet_fix_skips_empty_text():
    """No DB call when bullet text is blank."""
    with patch(
        "app.services.corpus_writer.async_session_factory"
    ) as mock_factory:
        await embed_bullet_fix(
            user_id=uuid.uuid4(),
            session_id="s",
            bullet_text="   ",
        )
    mock_factory.assert_not_called()


# ---------------------------------------------------------------------------
# embed_user_notes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_user_notes_section_type_is_none():
    user_id = uuid.uuid4()
    ctx, db = _make_db_ctx()
    added: list = []
    db.add = lambda obj: added.append(obj)

    with (
        patch("app.services.corpus_writer.async_session_factory", return_value=ctx),
        patch(
            "app.services.corpus_writer.embed_texts",
            new_callable=AsyncMock,
            return_value=[[0.3] * 1536],
        ),
    ):
        await embed_user_notes(
            user_id=user_id,
            session_id="sess",
            notes_text="I have 5 years with Kubernetes",
        )

    assert len(added) == 1
    assert added[0].section_type is None


@pytest.mark.asyncio
async def test_embed_user_notes_skips_empty():
    with patch("app.services.corpus_writer.async_session_factory") as mock_factory:
        await embed_user_notes(user_id=uuid.uuid4(), session_id=None, notes_text="")
    mock_factory.assert_not_called()


# ---------------------------------------------------------------------------
# embed_claimed_keywords
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_claimed_keywords_one_chunk_per_keyword():
    user_id = uuid.uuid4()
    ctx, db = _make_db_ctx()
    added: list = []
    db.add = lambda obj: added.append(obj)
    keywords = ["Kubernetes", "Terraform", "Python"]

    with (
        patch("app.services.corpus_writer.async_session_factory", return_value=ctx),
        patch(
            "app.services.corpus_writer.embed_texts",
            new_callable=AsyncMock,
            return_value=[[0.4] * 1536 for _ in keywords],
        ),
    ):
        await embed_claimed_keywords(
            user_id=user_id,
            session_id="s",
            keywords=keywords,
        )

    assert len(added) == 3
    assert all(c.corpus_source.value == "claimed_keyword" for c in added)


@pytest.mark.asyncio
async def test_embed_claimed_keywords_skips_all_empty():
    with patch("app.services.corpus_writer.async_session_factory") as mock_factory:
        await embed_claimed_keywords(
            user_id=uuid.uuid4(), session_id=None, keywords=["", "  "]
        )
    mock_factory.assert_not_called()


# ---------------------------------------------------------------------------
# Embedding fallback — zero-vector on provider error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_tailored_resume_fallback_on_embedding_error():
    """When the embedding provider fails, chunks are still stored with zero-vectors."""
    from app.services.master_resume.embedding import EmbeddingProviderError

    user_id = uuid.uuid4()
    ctx, db = _make_db_ctx()
    added: list = []
    db.add = lambda obj: added.append(obj)

    with (
        patch("app.services.corpus_writer.async_session_factory", return_value=ctx),
        patch(
            "app.services.corpus_writer.embed_texts",
            new_callable=AsyncMock,
            side_effect=EmbeddingProviderError("provider down"),
        ),
        patch(
            "app.services.corpus_writer._soft_delete_session_source",
            new_callable=AsyncMock,
        ),
    ):
        await embed_tailored_resume(
            user_id=user_id,
            session_id="sess",
            tailored_output=_fake_tailored_output(),
        )

    # Chunks are persisted even when embedding fails (zero-vector fallback).
    assert len(added) == 3
    for chunk in added:
        assert all(v == 0.0 for v in chunk.embedding)
