"""Retrieval defaults (IMPLEMENTATION_PLAN §6a "Source-of-truth for retrieval limits").

These are **compile-time constants** — the values here are the canonical
defaults used when no admin ``LLMConfig`` row is present.  At runtime
:mod:`app.services.retrieval.retrieval_service` reads the active
``LLMConfig`` row (when Step 35 lands) and overrides individual knobs;
any unset override falls back to the constant in this module.

Precedence rule (resolved in §6a):

    constants in this file
        <- LLMConfig row (admin-tunable, audited via AdminAuditLog)

No knob in this module is overridable via env vars — that is intentional
so all changes flow through the audited admin surface.  Tests that need
deterministic overrides should monkeypatch
:mod:`app.services.retrieval.retrieval_service.resolve_runtime_config`.
"""

from __future__ import annotations

from typing import Final

# Per-section maximum number of chunks selected for the Phase 3 prompt.
# Matches SYSTEM_DESIGN_PHASE_2 §18.4 "Apply per-section caps" plus the
# IMPLEMENTATION_PLAN §6a table.  Keys are :class:`MasterResumeSectionType`
# string values; ``"other"`` is the catch-all for ``cert / publication /
# award / volunteer / language / patent / other`` sections that share a
# small cap.
RETRIEVAL_CAPS: Final[dict[str, int]] = {
    "experience": 8,
    "project": 4,
    "education": 3,
    "skills": 6,
    "other": 4,
}

# Global token ceiling for the chunks portion of the Phase 3 prompt.
# Enforced after per-section caps; lowest-scoring chunks are dropped
# first, but the top-1 chunk of any qualifying section is *never* dropped
# (§6a "Retrieval algorithm" rule 5).
RETRIEVAL_TOKEN_BUDGET: Final[int] = 6000

# Cosine similarity threshold for the primary ANN pass.  Chunks scoring
# strictly below this are excluded.  Default 0.72 matches
# SYSTEM_DESIGN_PHASE_2 §18.4 step 3.
RETRIEVAL_PRIMARY_THRESHOLD: Final[float] = 0.72

# Relaxed threshold used when *no* chunk in a section passes the primary
# threshold.  Default 0.55 per §6a "Empty-result fallback" step 1.
RETRIEVAL_FALLBACK_THRESHOLD: Final[float] = 0.55

# Canonical embedding model id.  Persisted into ``retrieval_meta`` on
# every phase 3 run so snapshots can be replayed identically.  Changing
# this requires a migration that re-embeds existing chunks — never set
# it dynamically per request.
RETRIEVAL_EMBEDDING_MODEL: Final[str] = "text-embedding-3-small"

# Sections that we refuse to ship to Phase 3 with an empty chunk list —
# losing all experience or education chunks silently would produce
# nonsense output.  See §6a "Empty-result fallback" step 2.
CRITICAL_SECTIONS: Final[frozenset[str]] = frozenset({"experience", "education"})

# Sections we *can* safely omit from the prompt when retrieval finds
# nothing relevant (the LLM will simply not emit a section for them).
NON_CRITICAL_SECTIONS: Final[frozenset[str]] = frozenset(
    {"project", "skills", "other"}
)

# Maximum chunks pulled per critical section when the fallback path
# is forced past both thresholds.  ``min(RETRIEVAL_CAPS[section], 3)``
# is computed at runtime; this constant just documents the upper bound.
RETRIEVAL_FALLBACK_MAX_PER_CRITICAL_SECTION: Final[int] = 3

# Reserve so Phase 3 always has headroom to actually emit a tailored
# resume.  Subtracted from the model's input window before the prompt
# budget check (see §6a "Determinism and prompt budget contract").
PROMPT_OUTPUT_RESERVE_TOKENS: Final[int] = 1024


def section_cap(section: str) -> int:
    """Return the cap for ``section`` falling back to the ``other`` bucket.

    Anything not in ``RETRIEVAL_CAPS`` (``summary``, ``cert``,
    ``publication``, ``award``, ``volunteer``, ``language``, ``patent``,
    ``other``) is treated as the catch-all ``other`` row.
    """
    return RETRIEVAL_CAPS.get(section, RETRIEVAL_CAPS["other"])


def is_critical_section(section: str) -> bool:
    return section in CRITICAL_SECTIONS


__all__ = [
    "CRITICAL_SECTIONS",
    "NON_CRITICAL_SECTIONS",
    "PROMPT_OUTPUT_RESERVE_TOKENS",
    "RETRIEVAL_CAPS",
    "RETRIEVAL_EMBEDDING_MODEL",
    "RETRIEVAL_FALLBACK_MAX_PER_CRITICAL_SECTION",
    "RETRIEVAL_FALLBACK_THRESHOLD",
    "RETRIEVAL_PRIMARY_THRESHOLD",
    "RETRIEVAL_TOKEN_BUDGET",
    "is_critical_section",
    "section_cap",
]
