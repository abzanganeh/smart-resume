"""SQLAlchemy ORM model and Pydantic output schema for company intelligence.

The ``CompanyProfile`` table is populated by
:mod:`app.services.company_intel` when Phase 1 completes.  One row per
normalised company key (slug).  TTL is enforced at read time; there is no
scheduled purge job.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

try:
    from pydantic import BaseModel
except ImportError:  # pragma: no cover
    raise


# ---------------------------------------------------------------------------
# SQLAlchemy ORM
# ---------------------------------------------------------------------------


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid.uuid4,
    )
    company_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(500), nullable=False)
    mission: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    values: Mapped[list] = mapped_column(JSONB(), nullable=False, default=list)
    culture_notes: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    cached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Pydantic transfer object — used throughout the service layer and session
# ---------------------------------------------------------------------------


class CompanyIntelOutput(BaseModel):
    """Extracted company intelligence ready to be injected into a Phase 3 prompt."""

    company_name: str
    mission: str = ""
    values: list[str] = []
    culture_notes: str = ""
    # Indicates where the intel came from so the caller can log it.
    source: Literal["jd_text", "cache"] = "jd_text"

    def is_empty(self) -> bool:
        """True when none of the signal fields contain useful content."""
        return not (self.mission or self.values or self.culture_notes)

    def render_for_prompt(self) -> str:
        """Compact block injected into the Phase 3 system prompt."""
        parts: list[str] = [f"Company: {self.company_name}"]
        if self.mission:
            parts.append(f"Mission: {self.mission}")
        if self.values:
            parts.append("Values: " + ", ".join(self.values))
        if self.culture_notes:
            parts.append(f"Culture: {self.culture_notes}")
        return "\n".join(parts)
