"""Shared fixtures for Flint handoff / context unit tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.keywords import KeywordExtractionOutput, RoleContext
from app.models.rewrite import TailoredResumeOutput
from app.models.session import Session


def session_with_outputs(*, user_id: str | None = "user-1") -> Session:
    return Session(
        session_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
        user_id=user_id,
        jd_raw="Senior Engineer at Acme Corp\nBuild distributed systems.",
        phase1_output=KeywordExtractionOutput(
            role_context=RoleContext(
                career_level="senior",
                primary_domain="platform engineering",
            ),
        ),
        phase3_output=TailoredResumeOutput(
            contact={"name": "Alex", "title": "Senior Engineer"},
            summary="Experienced backend engineer.",
            skills=["Rust", "Python"],
        ),
    )
