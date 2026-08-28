"""LLMConfig — admin-tunable platform LLM routing per tier.

Single source of truth for the (provider, model_string) tuple used by
the Agent Phase 3 orchestrator's tier middleware (Step 19) and by
future admin overrides (Step 35 §19.7).

Each row addresses one canonical tier:

- ``standard`` — Gemini 2.5 Flash-Lite, used for every phase by default
  (Phase 1–4, fit, cover_letter).
- ``better``   — Gemini 2.5 Flash, used for Phase 3 only.
- ``best``     — Claude Sonnet 4.6, used for Phase 3 only.

The ``phases_enabled`` JSONB array is a ``list[str]`` whose values are
free-form phase identifiers ("1", "2", "3", "4", "fit", "cover_letter").
Stored as JSON so we can extend the catalog without an enum migration.

All hard-coded model strings in the codebase are anti-pattern (see
SYSTEM_DESIGN_PHASE_2 §18.9 model lifecycle note); the orchestrator
must read the value here at request time.

This table is bootstrapped at startup (`seed_llm_configs_if_empty`) so
fresh local dev / CI environments resolve a model without a manual
admin step.  Admin edits through the Step 35 UI write here directly
under the same audit pattern as ``PlanConfig`` (set ``is_active=False``
on the prior row, insert a new active row).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.billing import LLMUpgradeTier


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LLMProvider(str, enum.Enum):
    """Provider id used by ``app.llm.factory.get_llm_client``.

    Mirrors the ``LLM_PROVIDER`` literal in ``app/config.py`` so we can
    create a type-safe enum here without bringing in the wider config
    surface.
    """

    openai = "openai"
    anthropic = "anthropic"
    gemini = "gemini"
    openrouter = "openrouter"
    ollama = "ollama"
    deepseek = "deepseek"


_LLM_PROVIDER_PG = PGEnum(
    LLMProvider,
    name="llm_config_provider",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
_LLM_TIER_PG = PGEnum(
    LLMUpgradeTier,
    name="llm_upgrade_tier",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class LLMConfig(Base):
    """One row per LLM upgrade tier.

    Columns:
    - ``tier``           — primary key business value; one of standard/better/best.
    - ``provider``       — provider id understood by the LLM factory.
    - ``model_string``   — exact model identifier passed to the SDK
                           (``claude-sonnet-4-6``, ``gemini-2.5-flash-lite``).
    - ``phases_enabled`` — list of phase identifiers where this tier is
                           a valid routing target.  Phase 3 is the only
                           upgrade-eligible phase per §18.9 — the
                           ``standard`` row keeps the full set so the
                           orchestrator can use it for any phase.
    - ``is_active``      — admin can disable a tier without deleting
                           the row (preserving audit history).
    - ``created_by_admin_id`` — set by Step 35 admin writes; nullable
                           for boot-seeded rows.
    """

    __tablename__ = "llm_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tier: Mapped[LLMUpgradeTier] = mapped_column(
        _LLM_TIER_PG, nullable=False, index=True
    )
    provider: Mapped[LLMProvider] = mapped_column(
        _LLM_PROVIDER_PG, nullable=False
    )
    model_string: Mapped[str] = mapped_column(String(255), nullable=False)
    phases_enabled: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_by_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_llm_configs_tier_active", "tier", "is_active"),
        # Partial unique index: at most one ``is_active=true`` row per tier.
        # Multiple inactive (history) rows are allowed.
        Index(
            "uq_llm_configs_one_active_per_tier",
            "tier",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )


__all__ = [
    "LLMConfig",
    "LLMProvider",
]
