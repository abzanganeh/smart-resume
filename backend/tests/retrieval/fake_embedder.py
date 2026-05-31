"""Deterministic fake embedder used by the retrieval test suite.

We build a 1536-dim unit vector from a content-addressable "bag of
tokens" so that two strings sharing many tokens have higher cosine
similarity than two strings sharing few.  Crucially the vector is a
pure function of the input string, so retrieval traces are
byte-identical across runs (IMPLEMENTATION_PLAN §6a determinism
contract).

The implementation deliberately stays in pure Python (no numpy) so the
test suite has zero extra runtime dependencies.
"""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from app.models.master_resume import EMBEDDING_DIM


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


@lru_cache(maxsize=4096)
def _vector_for(text: str) -> tuple[float, ...]:
    """Return a deterministic 1536-dim unit vector for ``text``."""
    vec = [0.0] * EMBEDDING_DIM
    text = (text or "").strip().lower()
    if not text:
        # Match the production embedder's empty-string contract.
        return tuple(vec)

    tokens = _TOKEN_RE.findall(text)
    if not tokens:
        return tuple(vec)

    for token in tokens:
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        # Spread each token across 4 dims so the vector has enough
        # density to discriminate between texts.
        for offset in range(4):
            idx = int.from_bytes(digest[offset * 4 : offset * 4 + 4], "big") % EMBEDDING_DIM
            magnitude = (digest[offset] + 1) / 256.0  # 1/256 .. 1.0
            vec[idx] += magnitude

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return tuple(vec)


def deterministic_embed(texts, model):  # noqa: ARG001 — model is irrelevant here
    """Fake embedder matching the signature ``set_fake_embedder`` expects."""
    return [list(_vector_for(t)) for t in texts]


def zero_embedder(texts, model):  # noqa: ARG001
    """Always returns the zero vector — useful for forcing the fallback path."""
    return [[0.0] * EMBEDDING_DIM for _ in texts]


def cosine(a, b) -> float:
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(x * x for x in b))
    if da == 0 or db == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (da * db)
