"""StepLLMConfig — admin-tunable provider/model pin per pipeline step.

Each active row overrides ``STEP_DEFAULTS`` in ``model_registry`` for one
``PipelineStep``.  History is preserved by deactivating the prior row when
admin posts a new pin (same pattern as ``PlanConfig`` / ``LLMConfig``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.llm_config import LLMProvider, _LLM_PROVIDER_PG


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StepLLMConfig(Base):
    __tablename__ = "step_llm_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    step: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[LLMProvider] = mapped_column(
        _LLM_PROVIDER_PG, nullable=False
    )
    model_string: Mapped[str] = mapped_column(String(255), nullable=False)
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
        Index("ix_step_llm_configs_step_active", "step", "is_active"),
        Index(
            "uq_step_llm_configs_one_active_per_step",
            "step",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )


__all__ = ["StepLLMConfig"]
