"""Chunking policy for the master resume (SYSTEM_DESIGN_PHASE_2 §18.4).

The §18.4 table specifies one chunk granularity and max-chars-per-chunk
per section type:

    experience           one chunk per bullet              800 chars
    project              one chunk per project              1500 chars
    skills               one chunk per category group       400 chars
    education            one chunk per institution          600 chars
    cert / publication / award / patent / language          400 chars
    summary              whole summary as one chunk        1000 chars
    other / volunteer    catch-all                          400 chars

Chunks exceeding the cap are split on **sentence boundaries** with a
**50-character overlap** so the splitter never breaks a clause in half.
``tiktoken`` produces ``token_count`` per chunk for prompt-budget
accounting downstream.

The input ``parsed_sections`` shape is intentionally permissive so the
LLM-driven Phase 0 parser (already used by ``app/routers/resume.py``
``_structure_resume``) can hand its output here without an adapter.
Each section value is normalised into a list of ``{ "content": str,
"metadata": {...} }`` items before chunking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

import tiktoken

from app.models.master_resume import MasterResumeSectionType


# ---------------------------------------------------------------------------
# Per-section character caps (§18.4 table)
# ---------------------------------------------------------------------------

SECTION_CHAR_CAPS: dict[MasterResumeSectionType, int] = {
    MasterResumeSectionType.experience: 800,
    MasterResumeSectionType.project: 1500,
    MasterResumeSectionType.skills: 400,
    MasterResumeSectionType.education: 600,
    MasterResumeSectionType.cert: 400,
    MasterResumeSectionType.publication: 400,
    MasterResumeSectionType.award: 400,
    MasterResumeSectionType.patent: 400,
    MasterResumeSectionType.language: 400,
    MasterResumeSectionType.summary: 1000,
    MasterResumeSectionType.volunteer: 400,
    MasterResumeSectionType.other: 400,
}

# §18.4 "split on sentence boundaries with 50-char overlap"
OVERLAP_CHARS = 50

# tiktoken encoding shared by all OpenAI generation models — same family
# as ``text-embedding-3-small`` so the token counts reported for the
# embedding bill match the prompt-budget check downstream.
_TOKENIZER = tiktoken.get_encoding("cl100k_base")

# Naïve sentence splitter: break after . ! ? when followed by whitespace.
# Pre-existing newlines also count as boundaries because resume bullets
# rarely contain prose with multiple sentences.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(slots=True, frozen=True)
class Chunk:
    """A single chunk ready to be embedded and persisted.

    The router layer maps these into :class:`MasterResumeChunk` rows;
    keeping a plain dataclass here avoids dragging the ORM into the
    chunking unit test suite.
    """

    section_type: MasterResumeSectionType
    content: str
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


def count_tokens(text: str) -> int:
    """Return the ``cl100k_base`` token count for ``text``."""
    return len(_TOKENIZER.encode(text))


# ---------------------------------------------------------------------------
# Section input normalisation
# ---------------------------------------------------------------------------


def _normalise_section_items(
    section_type: MasterResumeSectionType,
    raw: Any,
) -> list[dict[str, Any]]:
    """Coerce arbitrary parsed-sections shapes into a list of dict items.

    Accepts:

    - ``str``                              → single item.
    - ``list[str]``                        → one item per string.
    - ``list[dict]`` with ``content`` keys → passed through.
    - ``list[dict]`` of structured rows    → flattened (see below).
    - ``dict``                             → wrapped as a single item.

    For structured ``experience``/``project``/``education`` dicts that
    don't carry a ``content`` field but do carry ``bullets``/``title``,
    each bullet becomes its own chunk and the title/company/year ride
    along in ``metadata`` for traceability.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [{"content": text, "metadata": {}}] if text else []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []

    items: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, str):
            text = entry.strip()
            if text:
                items.append({"content": text, "metadata": {}})
            continue
        if not isinstance(entry, dict):
            continue
        if "content" in entry and isinstance(entry["content"], str):
            text = entry["content"].strip()
            if text:
                items.append(
                    {
                        "content": text,
                        "metadata": entry.get("metadata", {}) or {},
                    }
                )
            continue

        # Structured experience/project/education shape.
        items.extend(_flatten_structured_entry(section_type, entry))
    return items


def _flatten_structured_entry(
    section_type: MasterResumeSectionType, entry: dict[str, Any]
) -> list[dict[str, Any]]:
    """Flatten the structured shape used by the resume parser."""
    metadata_base: dict[str, Any] = {}
    for key in ("company", "title", "role", "institution", "degree", "year", "dates"):
        value = entry.get(key)
        if value:
            metadata_base[key] = value
    extra_meta = entry.get("metadata")
    if isinstance(extra_meta, dict):
        metadata_base.update(extra_meta)

    bullets = entry.get("bullets")
    out: list[dict[str, Any]] = []

    if section_type == MasterResumeSectionType.experience and isinstance(bullets, list):
        for idx, bullet in enumerate(bullets):
            text = (bullet or "").strip() if isinstance(bullet, str) else ""
            if not text:
                continue
            meta = {**metadata_base, "bullet_index": idx}
            out.append({"content": text, "metadata": meta})
        return out

    if section_type == MasterResumeSectionType.project:
        # Project = header paragraph + bullets, joined into a single
        # chunk per §18.4 ("one chunk per project (header paragraph +
        # bullets)").  Splitter will break if it exceeds the 1500-char
        # cap.
        parts: list[str] = []
        for k in ("title", "name", "summary", "description"):
            v = entry.get(k)
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
        if isinstance(bullets, list):
            parts.extend(
                f"- {b.strip()}" for b in bullets if isinstance(b, str) and b.strip()
            )
        joined = "\n".join(parts).strip()
        if joined:
            out.append({"content": joined, "metadata": metadata_base})
        return out

    if section_type == MasterResumeSectionType.education:
        # One chunk per institution.  Compose ``institution — degree
        # (year)`` plus any bullets so the embedding has enough context.
        parts: list[str] = []
        header_bits: list[str] = []
        for k in ("institution", "school"):
            v = entry.get(k)
            if isinstance(v, str) and v.strip():
                header_bits.append(v.strip())
                break
        for k in ("degree", "field"):
            v = entry.get(k)
            if isinstance(v, str) and v.strip():
                header_bits.append(v.strip())
        for k in ("year", "dates", "graduation_year"):
            v = entry.get(k)
            if v:
                header_bits.append(str(v).strip())
                break
        if header_bits:
            parts.append(" — ".join(header_bits))
        if isinstance(bullets, list):
            parts.extend(
                f"- {b.strip()}" for b in bullets if isinstance(b, str) and b.strip()
            )
        joined = "\n".join(parts).strip()
        if joined:
            out.append({"content": joined, "metadata": metadata_base})
        return out

    # Fallback: stringify the entry's first meaningful field.
    for k in ("content", "name", "title", "summary", "description", "text"):
        v = entry.get(k)
        if isinstance(v, str) and v.strip():
            out.append({"content": v.strip(), "metadata": metadata_base})
            return out
    return out


# ---------------------------------------------------------------------------
# Sentence-aware splitter
# ---------------------------------------------------------------------------


def _split_with_overlap(text: str, max_chars: int) -> list[str]:
    """Split ``text`` into chunks no longer than ``max_chars``.

    Boundaries prefer sentence ends; the 50-char overlap preserves
    context across the boundary (§18.4).  Sentences longer than
    ``max_chars`` are hard-split at the cap as a last resort so the
    function never returns oversized chunks.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    pieces = [p.strip() for p in _SENTENCE_BOUNDARY.split(text) if p.strip()]
    if not pieces:
        # No detectable sentence boundary — hard-split with overlap.
        return _hard_split_with_overlap(text, max_chars)

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if len(piece) > max_chars:
            # Long sentence — flush current, then hard-split the piece.
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_hard_split_with_overlap(piece, max_chars))
            continue

        candidate = f"{current} {piece}".strip() if current else piece
        if len(candidate) <= max_chars:
            current = candidate
            continue

        # Adding the next sentence would overflow — flush and prime the
        # next chunk with an overlap so context isn't lost.
        chunks.append(current.strip())
        tail = current[-OVERLAP_CHARS:] if len(current) > OVERLAP_CHARS else current
        # Avoid producing a chunk that is just the overlap.
        prefix = f"{tail.strip()} " if tail.strip() else ""
        current = f"{prefix}{piece}".strip()

    if current:
        chunks.append(current.strip())

    return [c for c in chunks if c]


def _hard_split_with_overlap(text: str, max_chars: int) -> list[str]:
    """Fixed-width slicer with overlap — last-resort path."""
    if max_chars <= OVERLAP_CHARS:
        # Pathological config: just use disjoint slices.
        return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]

    step = max_chars - OVERLAP_CHARS
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end == len(text):
            break
        start += step
    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _coerce_section_type(value: str) -> MasterResumeSectionType:
    """Normalise human-friendly section labels to the canonical enum."""
    if isinstance(value, MasterResumeSectionType):
        return value
    key = (value or "").strip().lower()
    aliases = {
        "experiences": MasterResumeSectionType.experience,
        "work_experience": MasterResumeSectionType.experience,
        "employment": MasterResumeSectionType.experience,
        "projects": MasterResumeSectionType.project,
        "skill": MasterResumeSectionType.skills,
        "educations": MasterResumeSectionType.education,
        "certifications": MasterResumeSectionType.cert,
        "certificates": MasterResumeSectionType.cert,
        "publications": MasterResumeSectionType.publication,
        "awards": MasterResumeSectionType.award,
        "patents": MasterResumeSectionType.patent,
        "languages": MasterResumeSectionType.language,
        "volunteering": MasterResumeSectionType.volunteer,
        "contact": MasterResumeSectionType.other,
    }
    if key in aliases:
        return aliases[key]
    try:
        return MasterResumeSectionType(key)
    except ValueError:
        return MasterResumeSectionType.other


def chunk_parsed_sections(parsed_sections: dict[str, Any]) -> list[Chunk]:
    """Turn a parsed-sections payload into a flat list of :class:`Chunk`.

    Order is deterministic: sections in the order they appear in
    ``parsed_sections``, items in the order they appear within a
    section, and split pieces in left-to-right order.  This matches the
    determinism requirement of IMPLEMENTATION_PLAN §6a — the same input
    must always produce the same chunks (and therefore the same
    embedding rows, and therefore the same retrieval output).
    """
    out: list[Chunk] = []
    if not isinstance(parsed_sections, dict):
        return out

    for raw_key, raw_value in parsed_sections.items():
        section_type = _coerce_section_type(raw_key)
        items = _normalise_section_items(section_type, raw_value)
        cap = SECTION_CHAR_CAPS.get(section_type, 400)
        for item in items:
            content = (item.get("content") or "").strip()
            if not content:
                continue
            metadata = dict(item.get("metadata") or {})
            for piece in _split_with_overlap(content, cap):
                out.append(
                    Chunk(
                        section_type=section_type,
                        content=piece,
                        token_count=count_tokens(piece),
                        metadata=metadata,
                    )
                )
    return out


def chunk_raw_text(raw_text: str) -> list[Chunk]:
    """Fallback path when only the raw upload text is available.

    The whole document is treated as ``other`` and split with the
    ``other`` cap.  Used by the test suite and as an emergency path
    when the LLM-driven parser is unavailable — the parsed-sections
    flow above produces much better chunks in normal operation.
    """
    pieces = _split_with_overlap(
        raw_text, SECTION_CHAR_CAPS[MasterResumeSectionType.other]
    )
    return [
        Chunk(
            section_type=MasterResumeSectionType.other,
            content=p,
            token_count=count_tokens(p),
        )
        for p in pieces
    ]


def total_token_count(chunks: Iterable[Chunk]) -> int:
    return sum(c.token_count for c in chunks)


__all__ = [
    "Chunk",
    "OVERLAP_CHARS",
    "SECTION_CHAR_CAPS",
    "chunk_parsed_sections",
    "chunk_raw_text",
    "count_tokens",
    "total_token_count",
]
