"""OpenAI embedding client for the master-resume pipeline.

IMPLEMENTATION_PLAN §6a fixes the embedding model to
``text-embedding-3-small`` (1536-dim).  The OpenAI key used here is the
platform-owned ``OPENAI_EMBEDDING_KEY`` so a single canonical vector
space is shared by every user's chunks and every JD embedding — BYOK
chat keys never feed this path.

The module deliberately exposes two functions:

- :func:`embed_text` returns one vector for one string.
- :func:`embed_texts` returns one vector per input string, batching
  multiple texts in a single OpenAI call (cheaper + faster).  All
  retrieval-service ingestion paths should go through this batch
  variant; :func:`embed_text` exists mainly for the JD-side query and
  for tests.

A small in-process cache keyed by ``(model, text)`` avoids re-embedding
the same chunk twice in unit tests; production traffic naturally has
near-zero hit rate so the cache is bounded.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import Iterable

import structlog

from app.config import settings
from app.services.retrieval.config import RETRIEVAL_EMBEDDING_MODEL

log = structlog.get_logger("master_resume.embedding")


class EmbeddingConfigurationError(RuntimeError):
    """Raised when no OpenAI key is available for embedding calls."""


class EmbeddingProviderError(RuntimeError):
    """Raised when OpenAI returns an error or no embeddings."""


_CACHE_LIMIT = 4096
_cache: "OrderedDict[tuple[str, str], list[float]]" = OrderedDict()


def _resolve_api_key() -> str:
    """Return the embedding key, falling back to ``OPENAI_API_KEY``.

    Production-grade envs (``APP_ENV ∈ {ci, staging, production}``)
    require ``OPENAI_EMBEDDING_KEY`` to be set explicitly — sharing the
    chat key in production would tie embedding capacity to per-user
    BYOK keys and complicate auditability.  Local/development falls back
    so a single ``OPENAI_API_KEY`` suffices for dev loops.
    """
    explicit = (settings.OPENAI_EMBEDDING_KEY or "").strip()
    if explicit:
        return explicit
    fallback = (settings.OPENAI_API_KEY or "").strip()
    if not fallback:
        raise EmbeddingConfigurationError(
            "OPENAI_EMBEDDING_KEY is not set (and OPENAI_API_KEY is empty). "
            "See IMPLEMENTATION_PLAN §6a — master-resume embeddings require "
            "the platform-owned key."
        )
    return fallback


def _cache_get(key: tuple[str, str]) -> list[float] | None:
    value = _cache.get(key)
    if value is not None:
        # Refresh LRU position.
        _cache.move_to_end(key)
    return value


def _cache_put(key: tuple[str, str], value: list[float]) -> None:
    _cache[key] = value
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_LIMIT:
        _cache.popitem(last=False)


def _reset_cache_for_tests() -> None:
    """Wipe the in-process cache — used by tests after monkeypatching."""
    _cache.clear()


# ---------------------------------------------------------------------------
# Test/CI override hook
# ---------------------------------------------------------------------------

# Tests may set this to a callable ``(texts: list[str], model: str) ->
# list[list[float]]`` so the suite never hits the network.  When ``None``
# the real OpenAI SDK is used.
_EMBEDDING_FAKE: "callable | None" = None


def set_fake_embedder(fake: "callable | None") -> None:
    """Install or clear a deterministic embedder for tests.

    The fake receives the full batch and must return one vector per
    input string in the same order.  Tests should restore the previous
    value (``None``) in their teardown.
    """
    global _EMBEDDING_FAKE
    _EMBEDDING_FAKE = fake
    _reset_cache_for_tests()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def embed_text(text: str, *, model: str | None = None) -> list[float]:
    """Return the embedding vector for a single string."""
    vectors = await embed_texts([text], model=model)
    return vectors[0]


async def embed_texts(
    texts: list[str] | tuple[str, ...] | Iterable[str],
    *,
    model: str | None = None,
) -> list[list[float]]:
    """Batch-embed ``texts`` and return their vectors in input order.

    Empty / whitespace-only inputs return an all-zero vector with the
    correct dimensionality so the caller doesn't need a guard around
    every CRUD path.  This matches our soft-fail policy for malformed
    chunks — the retrieval ANN query will not match a zero vector
    above any sensible threshold so they are effectively skipped.
    """
    texts_list = [t if isinstance(t, str) else str(t) for t in texts]
    if not texts_list:
        return []

    model = model or RETRIEVAL_EMBEDDING_MODEL

    # Cache-first pass.
    results: list[list[float] | None] = [None] * len(texts_list)
    missing_indices: list[int] = []
    missing_texts: list[str] = []
    for idx, text in enumerate(texts_list):
        stripped = text.strip()
        if not stripped:
            results[idx] = _zero_vector()
            continue
        cached = _cache_get((model, stripped))
        if cached is not None:
            results[idx] = cached
            continue
        missing_indices.append(idx)
        missing_texts.append(stripped)

    if missing_texts:
        fresh = await _call_embedding_api(missing_texts, model)
        if len(fresh) != len(missing_texts):
            raise EmbeddingProviderError(
                f"embedding provider returned {len(fresh)} vectors for "
                f"{len(missing_texts)} inputs"
            )
        for idx, vec, text in zip(missing_indices, fresh, missing_texts):
            _cache_put((model, text), vec)
            results[idx] = vec

    # By construction every slot is filled at this point.
    return [vec if vec is not None else _zero_vector() for vec in results]


async def _call_embedding_api(texts: list[str], model: str) -> list[list[float]]:
    if _EMBEDDING_FAKE is not None:
        return _EMBEDDING_FAKE(texts, model)

    # Import lazily so unit tests that monkeypatch ``set_fake_embedder``
    # never pay the import cost of the openai SDK.
    from openai import AsyncOpenAI

    api_key = _resolve_api_key()
    # ``base_url=None`` uses the default OpenAI endpoint; explicitly
    # disable env-driven org/project so dev machines without OPENAI_ORG
    # set behave identically to CI.
    client = AsyncOpenAI(
        api_key=api_key,
        organization=os.environ.get("OPENAI_ORG_ID") or None,
    )
    try:
        response = await client.embeddings.create(model=model, input=texts)
    except Exception as exc:  # noqa: BLE001 — re-raise as structured error
        log.error("embedding_call_failed", model=model, batch_size=len(texts), error=str(exc))
        raise EmbeddingProviderError(f"embedding provider error: {exc}") from exc

    if not response.data or len(response.data) != len(texts):
        raise EmbeddingProviderError(
            f"embedding provider returned malformed response "
            f"(expected {len(texts)} vectors, got {len(response.data or [])})"
        )
    return [list(d.embedding) for d in response.data]


def _zero_vector() -> list[float]:
    # 1536 dims must stay in sync with ``MasterResumeChunk.embedding``.
    from app.models.master_resume import EMBEDDING_DIM

    return [0.0] * EMBEDDING_DIM


__all__ = [
    "EmbeddingConfigurationError",
    "EmbeddingProviderError",
    "embed_text",
    "embed_texts",
    "set_fake_embedder",
]
