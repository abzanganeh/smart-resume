"""Test fixtures for the master-resume retrieval suite.

These tests require:

- A live Postgres with the ``vector`` extension and the ``0003`` migration
  applied (the project's ``db_session`` fixture already enforces this).
- A *fake* embedder so the suite is deterministic and never hits the
  OpenAI API.  We register a content-aware hash embedder that produces
  the same vector for the same input string, so two retrieval calls
  against the same input return byte-identical traces.

The fake embedder lives in :mod:`tests.retrieval.fake_embedder` so it
can be imported from individual test modules that want to customise
the behaviour (e.g. force all chunks below the primary threshold for
the fallback test).
"""

from __future__ import annotations

import pytest

from app.services.master_resume.embedding import set_fake_embedder
from tests.retrieval.fake_embedder import deterministic_embed


@pytest.fixture(autouse=True)
def install_deterministic_embedder():
    """Auto-install a deterministic embedder for every retrieval test.

    Individual tests may swap in a different fake via
    :func:`app.services.master_resume.embedding.set_fake_embedder`;
    teardown always restores ``None`` so subsequent suites are not
    affected by leftover state.
    """
    set_fake_embedder(deterministic_embed)
    try:
        yield
    finally:
        set_fake_embedder(None)
