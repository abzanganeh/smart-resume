from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

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


class Session(BaseModel):
    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    resume_raw: str | None = None
    resume_parsed: ParsedResume | None = None
    user_info: UserInfo | None = None
    jd_raw: str | None = None
    provider: str | None = None
    model: str | None = None
    # Ephemeral — user-supplied API key (BYOK). Never logged. Cleared on session expiry.
    byok_api_key: str | None = None

    phase1_status: PhaseStatus = PhaseStatus.pending
    phase1_output: KeywordExtractionOutput | None = None

    phase2_status: PhaseStatus = PhaseStatus.pending
    phase2_output: AuditOutput | None = None

    phase3_status: PhaseStatus = PhaseStatus.pending
    phase3_output: TailoredResumeOutput | None = None
    phase3_versions: list[ResumeVersion] = []

    phase4_status: PhaseStatus = PhaseStatus.pending
    phase4_output: QAOutput | None = None
