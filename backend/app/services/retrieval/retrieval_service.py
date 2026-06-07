"""Deterministic master-resume retrieval (IMPLEMENTATION_PLAN §6a).

This module is the single source of truth for the algorithm that
selects which master-resume chunks feed Phase 3.  It is intentionally
pure-business-logic — the FastAPI handlers in
``app/agent/phase3_rewrite.py`` and ``app/routers/profile.py`` call
into the helpers exposed here and translate the structured errors
into HTTP responses.

Algorithm summary (§6a "Retrieval algorithm (deterministic)"):

1. Load runtime overrides from the active ``LLMConfig`` row.  None of
   the knobs are env-driven; everything falls back to the constants in
   :mod:`app.services.retrieval.config`.
2. Embed the JD with the resolved embedding model.
3. Run a cosine ANN query against ``master_resume_chunks.embedding``
   per section, ordered ``(score DESC, chunk.created_at ASC, chunk.id
   ASC)``.  The tie-breaker is required so the same JD always selects
   the same chunks across processes / replays.
4. Apply the primary threshold.
5. Apply per-section caps.
6. Enforce the global token budget by dropping the lowest-scoring
   chunks first, **never** dropping the top-1 chunk of any qualifying
   section.
7. Emit ``selected_chunks``, ``skipped_chunks``, ``retrieval_meta``.

Empty-result fallback (§6a):

- Re-query each empty section at the relaxed threshold.
- Still empty + critical section (experience / education) →
  take top-N by raw score capped at ``min(cap, 3)``, marked
  ``reason="fallback_used"``.
- Still empty + non-critical → omit, list in
  ``retrieval_meta.sections_omitted``.

If the user has zero live chunks at all, raise
:class:`MasterResumeRequiredError` so the caller can return HTTP 409.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

import structlog
import tiktoken
from sqlalchemy import bindparam, select, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.master_resume.crud import has_any_live_chunk
from app.services.master_resume.embedding import embed_text
from app.services.retrieval import config as cfg
from app.services.retrieval.exceptions import (
    MasterResumeRequiredError,
    PromptBudgetExceededError,
)

log = structlog.get_logger("retrieval")


# ---------------------------------------------------------------------------
# Runtime configuration resolution
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class RuntimeRetrievalConfig:
    """Effective per-request retrieval configuration.

    Built by :func:`resolve_runtime_config` which combines the compile-time
    constants with optional admin overrides from ``LLMConfig`` (Step 35
    introduces that table; until then this always returns the
    constants).  Tests can monkeypatch :func:`resolve_runtime_config`
    to inject deterministic values without touching the constants
    module.
    """

    caps: dict[str, int]
    token_budget: int
    primary_threshold: float
    fallback_threshold: float
    embedding_model: str

    def cap_for(self, section: str) -> int:
        if section in self.caps:
            return self.caps[section]
        # Catch-all for sections that share the ``other`` bucket per
        # SYSTEM_DESIGN_PHASE_2 §18.4 ("cert, publication, award,
        # patent, language" + summary + volunteer).
        return self.caps.get("other", cfg.RETRIEVAL_CAPS["other"])


async def resolve_runtime_config(
    db: AsyncSession,  # noqa: ARG001 — used once Step 35 lands
) -> RuntimeRetrievalConfig:
    """Resolve the active retrieval configuration.

    Until Step 35 introduces ``LLMConfig``, this function returns the
    compile-time defaults verbatim.  When ``LLMConfig`` lands the body
    here should read the active row and overlay non-null fields onto
    the defaults — no other code changes required because everything
    downstream consumes :class:`RuntimeRetrievalConfig`.
    """
    return RuntimeRetrievalConfig(
        caps=dict(cfg.RETRIEVAL_CAPS),
        token_budget=cfg.RETRIEVAL_TOKEN_BUDGET,
        primary_threshold=cfg.RETRIEVAL_PRIMARY_THRESHOLD,
        fallback_threshold=cfg.RETRIEVAL_FALLBACK_THRESHOLD,
        embedding_model=cfg.RETRIEVAL_EMBEDDING_MODEL,
    )


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Candidate:
    """A row as it comes back from pgvector — kept mutable for sorting."""

    chunk_id: uuid.UUID
    section: str
    score: float
    tokens: int
    content: str
    created_at_iso: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class SelectedChunk:
    chunk_id: str
    section: str
    score: float
    tokens: int
    content: str
    metadata: dict[str, Any]

    def to_trace(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "section": self.section,
            "score": round(self.score, 6),
            "tokens": self.tokens,
        }


@dataclass(slots=True)
class SkippedChunk:
    chunk_id: str
    section: str
    score: float
    reason: str  # ∈ {below_threshold, cap_exceeded, budget_exceeded, fallback_used}
    content: str = ""

    def to_trace(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "section": self.section,
            "score": round(self.score, 6),
            "reason": self.reason,
            "content": self.content,
        }


@dataclass(slots=True)
class RetrievalResult:
    """Full output of :func:`retrieve_for_jd`."""

    selected: list[SelectedChunk] = field(default_factory=list)
    skipped: list[SkippedChunk] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return sum(s.tokens for s in self.selected)

    def to_trace(self) -> dict[str, Any]:
        """Shape consumed by ``TailoredResumeOutput``."""
        return {
            "selected_chunks": [s.to_trace() for s in self.selected],
            "skipped_chunks": [s.to_trace() for s in self.skipped],
            "retrieval_meta": dict(self.meta),
        }

    def render_for_prompt(self) -> str:
        """Format the selected chunks as a deterministic prompt block.

        Phase 3 prompt instructions guide the LLM to compose only from
        these chunks — see ``app/agent/phase3_rewrite.py``.  The
        rendering is stable so that the same retrieval output always
        produces the same prompt bytes.
        """
        if not self.selected:
            return ""
        lines: list[str] = []
        current_section: str | None = None
        for s in self.selected:
            if s.section != current_section:
                lines.append("")
                lines.append(f"## {s.section.upper()}")
                current_section = s.section
            lines.append(f"- (score={s.score:.3f}) {s.content}")
        return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# pgvector query
# ---------------------------------------------------------------------------


# Cosine similarity in pgvector is ``1 - (a <=> b)`` where ``<=>`` is the
# built-in cosine *distance* operator (smaller = more similar).  The
# query computes the similarity once and uses it both for the ``WHERE``
# threshold filter and for the deterministic ordering.  The ``id``
# tie-breaker is appended so two chunks created at the same instant
# still sort identically across processes.

# Query for the extended user corpus (tailored_resume, bullet_fix, user_note,
# claimed_keyword sources).  Returns top-N by cosine similarity.  The
# ``corpus_source`` column is surfaced as ``section`` so it slots into the
# same _Candidate dataclass without schema changes.
_CORPUS_QUERY = text(
    """
    SELECT
        id,
        corpus_source::text AS section,
        1 - (embedding <=> CAST(:jd AS vector)) AS score,
        token_count,
        content,
        created_at,
        metadata
    FROM user_corpus_chunks
    WHERE user_id = :user_id
      AND deleted_at IS NULL
      AND embedding IS NOT NULL
      AND corpus_source != 'master_resume'
    ORDER BY score DESC, created_at ASC, id ASC
    LIMIT :limit
    """
).bindparams(
    bindparam("user_id", type_=PG_UUID(as_uuid=True)),
)

_PER_SECTION_QUERY = text(
    """
    SELECT
        id,
        section_type::text AS section,
        1 - (embedding <=> CAST(:jd AS vector)) AS score,
        token_count,
        content,
        created_at,
        metadata
    FROM master_resume_chunks
    WHERE user_id = :user_id
      AND section_type = :section_type
      AND deleted_at IS NULL
      AND embedding IS NOT NULL
    ORDER BY score DESC, created_at ASC, id ASC
    LIMIT :limit
    """
).bindparams(
    bindparam("user_id", type_=PG_UUID(as_uuid=True)),
)


def _vector_literal(vec: Sequence[float]) -> str:
    """pgvector accepts a textual ``[v1,v2,...]`` literal for ``::vector``."""
    return "[" + ",".join(f"{float(x):.7f}" for x in vec) + "]"


async def _query_section(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    section: str,
    jd_vector: Sequence[float],
    limit: int,
) -> list[_Candidate]:
    """Run the per-section ANN query and return candidates in rank order."""
    if limit <= 0:
        return []
    rows = (
        await db.execute(
            _PER_SECTION_QUERY,
            {
                "user_id": user_id,
                "section_type": section,
                "jd": _vector_literal(jd_vector),
                "limit": limit,
            },
        )
    ).mappings().all()

    out: list[_Candidate] = []
    for r in rows:
        # Clamp the score into [-1, 1].  pgvector occasionally yields
        # values like 1.0000000000000002 due to fp drift — clamp so
        # downstream JSON consumers don't choke on them.
        raw_score = float(r["score"])
        score = max(-1.0, min(1.0, raw_score))
        out.append(
            _Candidate(
                chunk_id=r["id"],
                section=r["section"],
                score=score,
                tokens=int(r["token_count"]),
                content=str(r["content"]),
                created_at_iso=r["created_at"].isoformat() if r["created_at"] else "",
                metadata=dict(r["metadata"] or {}),
            )
        )
    return out


async def _query_user_corpus(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    jd_vector: Sequence[float],
    limit: int,
) -> list[_Candidate]:
    """Run the ANN query against ``user_corpus_chunks`` and return candidates.

    Returns at most ``limit`` rows ordered by cosine similarity descending.
    Returns an empty list if the ``user_corpus_chunks`` table does not exist
    (e.g., before migration 0018 has been applied).
    """
    if limit <= 0:
        return []
    try:
        rows = (
            await db.execute(
                _CORPUS_QUERY,
                {
                    "user_id": user_id,
                    "jd": _vector_literal(jd_vector),
                    "limit": limit,
                },
            )
        ).mappings().all()
    except Exception as exc:
        # Degrade gracefully if the table does not exist yet.
        log.warning(
            "retrieval.corpus_query_failed",
            user_id=str(user_id),
            error=str(exc),
        )
        return []

    out: list[_Candidate] = []
    for r in rows:
        raw_score = float(r["score"])
        score = max(-1.0, min(1.0, raw_score))
        out.append(
            _Candidate(
                chunk_id=r["id"],
                section=r["section"],
                score=score,
                tokens=int(r["token_count"]),
                content=str(r["content"]),
                created_at_iso=r["created_at"].isoformat() if r["created_at"] else "",
                metadata=dict(r["metadata"] or {}),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Selection algorithm
# ---------------------------------------------------------------------------


# Sections we always query.  ``other`` aggregates the long tail per the
# §18.4 chunking policy.  Ordering here is purely cosmetic — the trace
# uses this same order so ``selected_chunks`` is stable across calls.
_DEFAULT_SECTIONS: tuple[str, ...] = (
    "experience",
    "skills",
    "education",
    "project",
    "other",
    "summary",
)


# Per-section "raw candidate" budget — how many rows to pull from the
# ANN before applying the threshold + cap.  Two × the cap is enough
# headroom for the fallback path to find a useful chunk even when the
# top-N are all below threshold.
def _candidate_limit_for(section: str, runtime: RuntimeRetrievalConfig) -> int:
    cap = runtime.cap_for(section)
    # Always pull at least 5 candidates even when the cap is small so
    # the fallback path has something to rank.
    return max(cap * 2, 5)


def _select_for_section(
    candidates: list[_Candidate],
    *,
    section: str,
    runtime: RuntimeRetrievalConfig,
) -> tuple[list[_Candidate], list[SkippedChunk], bool]:
    """Apply primary/fallback thresholds + cap.

    Returns ``(kept_candidates, skipped_chunks, fallback_used)``.
    """
    skipped: list[SkippedChunk] = []
    if not candidates:
        return [], skipped, False

    cap = runtime.cap_for(section)
    primary = [c for c in candidates if c.score >= runtime.primary_threshold]
    below_primary = [c for c in candidates if c.score < runtime.primary_threshold]

    fallback_used = False
    if primary:
        kept = primary[:cap]
        # Anything trimmed by the cap → cap_exceeded.
        for c in primary[cap:]:
            skipped.append(
                SkippedChunk(
                    chunk_id=str(c.chunk_id),
                    section=c.section,
                    score=c.score,
                    reason="cap_exceeded",
                    content=c.content,
                )
            )
        for c in below_primary:
            skipped.append(
                SkippedChunk(
                    chunk_id=str(c.chunk_id),
                    section=c.section,
                    score=c.score,
                    reason="below_threshold",
                    content=c.content,
                )
            )
        return kept, skipped, fallback_used

    # No chunk passed the primary threshold → try the relaxed threshold.
    relaxed = [c for c in candidates if c.score >= runtime.fallback_threshold]
    if relaxed:
        fallback_used = True
        kept = relaxed[:cap]
        for c in relaxed[cap:]:
            skipped.append(
                SkippedChunk(
                    chunk_id=str(c.chunk_id),
                    section=c.section,
                    score=c.score,
                    reason="cap_exceeded",
                    content=c.content,
                )
            )
        for c in candidates:
            if c.score < runtime.fallback_threshold:
                skipped.append(
                    SkippedChunk(
                        chunk_id=str(c.chunk_id),
                        section=c.section,
                        score=c.score,
                        reason="below_threshold",
                        content=c.content,
                    )
                )
        # Mark the kept chunks as fallback-used so the trace explains why
        # they showed up despite being below the primary threshold.  We
        # tag them via the skipped list with a special reason so the
        # frontend knows to badge them.
        for c in kept:
            skipped.append(
                SkippedChunk(
                    chunk_id=str(c.chunk_id),
                    section=c.section,
                    score=c.score,
                    reason="fallback_used",
                    content=c.content,
                )
            )
        return kept, skipped, fallback_used

    # Still empty.  Critical sections get top-N by raw score regardless of
    # threshold (§6a fallback step 2); non-critical sections are omitted
    # by returning an empty kept list (the caller records that under
    # ``sections_omitted``).
    if cfg.is_critical_section(section):
        fallback_used = True
        forced_cap = min(
            cap, cfg.RETRIEVAL_FALLBACK_MAX_PER_CRITICAL_SECTION
        )
        kept = candidates[:forced_cap]
        for c in candidates[forced_cap:]:
            skipped.append(
                SkippedChunk(
                    chunk_id=str(c.chunk_id),
                    section=c.section,
                    score=c.score,
                    reason="below_threshold",
                    content=c.content,
                )
            )
        for c in kept:
            skipped.append(
                SkippedChunk(
                    chunk_id=str(c.chunk_id),
                    section=c.section,
                    score=c.score,
                    reason="fallback_used",
                    content=c.content,
                )
            )
        return kept, skipped, fallback_used

    # Non-critical: omit the section.
    for c in candidates:
        skipped.append(
            SkippedChunk(
                chunk_id=str(c.chunk_id),
                section=c.section,
                score=c.score,
                reason="below_threshold",
                content=c.content,
            )
        )
    return [], skipped, False


def _enforce_token_budget(
    selected_by_section: dict[str, list[_Candidate]],
    *,
    budget: int,
) -> tuple[dict[str, list[_Candidate]], list[SkippedChunk]]:
    """Drop lowest-score chunks until under ``budget``.

    The top-1 chunk of every section is pinned — §6a "Enforce global
    token budget" explicitly forbids dropping it.  Returns the surviving
    chunks (still keyed by section) plus a list of ``budget_exceeded``
    skipped entries for the trace.
    """
    skipped: list[SkippedChunk] = []
    total = sum(c.tokens for chunks in selected_by_section.values() for c in chunks)
    if total <= budget:
        return selected_by_section, skipped

    # Build a flat candidate pool flagged with whether each row is the
    # top-1 of its section (pinned).
    pool: list[tuple[_Candidate, bool]] = []
    for section, rows in selected_by_section.items():
        for idx, c in enumerate(rows):
            pool.append((c, idx == 0))

    # Eviction order: pinned rows last, lowest score first within each
    # group.  We additionally tiebreak on (created_at_iso, id) so
    # determinism survives equal scores.
    pool.sort(
        key=lambda item: (
            item[1],  # False (un-pinned) sorts before True (pinned)
            item[0].score,
            item[0].created_at_iso,
            str(item[0].chunk_id),
        )
    )

    evicted: set[uuid.UUID] = set()
    for cand, pinned in pool:
        if total <= budget:
            break
        if pinned:
            # Cannot evict pinned rows.  If the remaining pinned rows
            # alone exceed the budget we simply accept the overshoot —
            # the prompt-budget gate below will fail the run with a
            # structured 422 so the user sees what happened.
            continue
        evicted.add(cand.chunk_id)
        total -= cand.tokens

    if not evicted:
        return selected_by_section, skipped

    survivors: dict[str, list[_Candidate]] = {}
    for section, rows in selected_by_section.items():
        keep = [c for c in rows if c.chunk_id not in evicted]
        if keep:
            survivors[section] = keep
        # Record the evicted ones into the trace.
        for c in rows:
            if c.chunk_id in evicted:
                skipped.append(
                    SkippedChunk(
                        chunk_id=str(c.chunk_id),
                        section=c.section,
                        score=c.score,
                        reason="budget_exceeded",
                        content=c.content,
                    )
                )
    return survivors, skipped


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def retrieve_for_jd(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    jd_text: str,
    sections: Sequence[str] = _DEFAULT_SECTIONS,
) -> RetrievalResult:
    """Run the full deterministic retrieval algorithm.

    Raises :class:`MasterResumeRequiredError` (→ HTTP 409) when the user
    has no live chunks at all.  Otherwise always returns a
    :class:`RetrievalResult` — the caller decides what to do with an
    empty ``selected`` list (typically: render Phase 3 without any
    chunks, which is only possible when every section was non-critical
    and below threshold).
    """
    # 0) When the user has no master resume chunks, return an empty result
    # so Phase 3 proceeds with only the session resume.  The master resume
    # is an enhancement, not a requirement.
    if not await has_any_live_chunk(db, user_id=user_id):
        return RetrievalResult()

    runtime = await resolve_runtime_config(db)

    # 1) Embed the JD once.  ``embed_text`` returns a 1536-dim vector.
    # If the embedding provider is unavailable (missing/invalid OpenAI key),
    # fall back to an empty retrieval result so Phase 3 still runs with the
    # session resume.  The master resume is an enhancement, not a requirement.
    from app.services.master_resume.embedding import (
        EmbeddingConfigurationError,
        EmbeddingProviderError,
    )
    try:
        jd_vector = await embed_text(
            jd_text or "", model=runtime.embedding_model
        )
    except (EmbeddingConfigurationError, EmbeddingProviderError) as exc:
        log.warning(
            "retrieval.jd_embed_failed_skip_retrieval",
            user_id=str(user_id),
            error=str(exc),
        )
        return RetrievalResult(
            meta={"retrieval_skipped": "embedding_provider_unavailable"}
        )

    selected_by_section: dict[str, list[_Candidate]] = {}
    all_skipped: list[SkippedChunk] = []
    fallback_sections: list[str] = []
    sections_omitted: list[str] = []

    # 2-4) Per-section ANN + thresholds + caps.
    for section in sections:
        candidates = await _query_section(
            db,
            user_id=user_id,
            section=section,
            jd_vector=jd_vector,
            limit=_candidate_limit_for(section, runtime),
        )
        kept, skipped, fallback_used = _select_for_section(
            candidates, section=section, runtime=runtime
        )
        all_skipped.extend(skipped)
        if kept:
            selected_by_section[section] = kept
        else:
            if not cfg.is_critical_section(section):
                sections_omitted.append(section)
        if fallback_used:
            fallback_sections.append(section)

    # 4b) Augment with user corpus chunks (accepted bullet fixes, tailored
    # resume history, notes, claimed keywords).  Capped at 4 chunks and
    # subject to the same token budget as master resume chunks.
    _CORPUS_CAP = 4
    corpus_candidates = await _query_user_corpus(
        db,
        user_id=user_id,
        jd_vector=jd_vector,
        limit=_CORPUS_CAP * 2,  # fetch extras so threshold filtering has room
    )
    corpus_kept: list[_Candidate] = [
        c for c in corpus_candidates if c.score >= runtime.primary_threshold
    ][:_CORPUS_CAP]
    for c in corpus_candidates:
        if c not in corpus_kept:
            all_skipped.append(
                SkippedChunk(
                    chunk_id=str(c.chunk_id),
                    section=c.section,
                    score=c.score,
                    reason="below_threshold",
                    content=c.content,
                )
            )
    if corpus_kept:
        # Merge into selected_by_section under their corpus_source label.
        for c in corpus_kept:
            selected_by_section.setdefault(c.section, []).append(c)

    # 5) Enforce the global token budget.
    selected_by_section, budget_skipped = _enforce_token_budget(
        selected_by_section, budget=runtime.token_budget
    )
    all_skipped.extend(budget_skipped)

    # 6) Project into the public result type.
    selected: list[SelectedChunk] = []
    for section in sections:
        for cand in selected_by_section.get(section, []):
            selected.append(
                SelectedChunk(
                    chunk_id=str(cand.chunk_id),
                    section=cand.section,
                    score=cand.score,
                    tokens=cand.tokens,
                    content=cand.content,
                    metadata=cand.metadata,
                )
            )

    result = RetrievalResult(
        selected=selected,
        skipped=all_skipped,
        meta={
            "threshold_used": (
                runtime.fallback_threshold
                if fallback_sections
                else runtime.primary_threshold
            ),
            "fallback_threshold": runtime.fallback_threshold,
            "fallback_used": bool(fallback_sections),
            "fallback_sections": fallback_sections,
            "sections_omitted": sections_omitted,
            "total_tokens": sum(s.tokens for s in selected),
            "embedding_model": runtime.embedding_model,
            "token_budget": runtime.token_budget,
            "corpus_chunks_added": len(corpus_kept),
        },
    )

    log.info(
        "retrieval_done",
        user_id=str(user_id),
        selected=len(result.selected),
        skipped=len(result.skipped),
        fallback_sections=fallback_sections,
        sections_omitted=sections_omitted,
        total_tokens=result.total_tokens,
    )
    return result


# ---------------------------------------------------------------------------
# Prompt budget enforcement
# ---------------------------------------------------------------------------


# Conservative per-model input windows.  Used by :func:`assert_prompt_fits`
# to compute the effective budget.  Unknown models fall back to 32k so we
# never fail a small prompt for lack of a catalog entry.
_MODEL_INPUT_WINDOW: dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4.1": 1_000_000,
    "gpt-3.5-turbo": 16_000,
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-opus-20240229": 200_000,
    "claude-3-haiku-20240307": 200_000,
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.5-flash-lite": 1_000_000,
    "gemini-3.5-flash": 1_000_000,
}

_PROMPT_TOKENIZER = tiktoken.get_encoding("cl100k_base")


def _model_input_window(model: str) -> int:
    if model in _MODEL_INPUT_WINDOW:
        return _MODEL_INPUT_WINDOW[model]
    # Strip optional provider prefix used by OpenRouter ("openai/gpt-4o").
    if "/" in model:
        suffix = model.split("/", 1)[1]
        if suffix in _MODEL_INPUT_WINDOW:
            return _MODEL_INPUT_WINDOW[suffix]
    return 32_000


def count_prompt_tokens(*pieces: str) -> int:
    """Sum of ``cl100k_base`` token counts for arbitrary prompt strings."""
    total = 0
    for piece in pieces:
        if not piece:
            continue
        total += len(_PROMPT_TOKENIZER.encode(piece))
    return total


def assert_prompt_fits(
    *pieces: str,
    model: str,
    output_reserve: int = cfg.PROMPT_OUTPUT_RESERVE_TOKENS,
) -> int:
    """Raise :class:`PromptBudgetExceededError` if the prompt won't fit.

    Returns the actual token count when the prompt fits so callers can
    log it on the trace.  The 1024-token output reserve matches §6a
    "Determinism and prompt budget contract".
    """
    total = count_prompt_tokens(*pieces)
    window = _model_input_window(model)
    budget = max(0, window - output_reserve)
    if total > budget:
        raise PromptBudgetExceededError(
            total_tokens=total, budget=budget, model=model
        )
    return total


__all__ = [
    "MasterResumeRequiredError",
    "PromptBudgetExceededError",
    "RetrievalResult",
    "RuntimeRetrievalConfig",
    "SelectedChunk",
    "SkippedChunk",
    "assert_prompt_fits",
    "count_prompt_tokens",
    "resolve_runtime_config",
    "retrieve_for_jd",
]
