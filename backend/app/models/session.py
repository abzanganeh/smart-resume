from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.models.audit import AuditOutput
from app.models.keywords import KeywordExtractionOutput
from app.models.qa import QAOutput
from app.models.resume import ParsedResume
from app.models.rewrite import ResumeVersion, TailoredResumeOutput
from app.models.userinfo import UserInfo


class PhaseStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"


class PhaseRunScope(BaseModel):
    """Optional scope for Phase 3 scoped regeneration (§18.5)."""

    section: str
    bullet_index: int | None = None
    company: str | None = None
    institution: str | None = None
    chunk_id: str | None = None
    chunk_content: str | None = None
    mode: Literal["regen", "add"] = "regen"


class Session(BaseModel):
    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # User id (UUID as string) — set when the session is opened by an
    # authenticated user.  Legacy anonymous demo sessions leave it
    # ``None``; retrieval-based Phase 3 is only run when ``user_id`` is
    # present (see ``app/agent/phase3_rewrite.py``).
    user_id: str | None = None

    resume_raw: str | None = None
    resume_parsed: ParsedResume | None = None
    user_info: UserInfo | None = None
    jd_raw: str | None = None
    provider: str | None = None
    model: str | None = None
    # Ephemeral — user-supplied API key (BYOK). Never logged. Cleared on session expiry.
    byok_api_key: str | None = None

    # User-declared additions: skills/keywords they have but weren't in the original resume
    user_claimed_keywords: list[str] = []
    user_extra_notes: str = ""  # free-text: "I also have experience with X and Y"

    phase1_status: PhaseStatus = PhaseStatus.pending
    phase1_output: KeywordExtractionOutput | None = None

    phase2_status: PhaseStatus = PhaseStatus.pending
    phase2_output: AuditOutput | None = None

    phase3_status: PhaseStatus = PhaseStatus.pending
    phase3_output: TailoredResumeOutput | None = None
    phase3_versions: list[ResumeVersion] = []

    phase4_status: PhaseStatus = PhaseStatus.pending
    phase4_output: QAOutput | None = None

    # Set by POST /phases/{n}/run so SSE knows to execute instead of replaying cache.
    phase_run_requested: int | None = None
    phase_run_scope: PhaseRunScope | None = None

    # Stale markers — set when upstream phase output is manually edited (§18.6).
    stale_since: datetime | None = None
    phase3_stale_since: datetime | None = None
    phase4_stale_since: datetime | None = None
