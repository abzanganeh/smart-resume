from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.agent.tone_profile import JDToneProfile


class Keyword(BaseModel):
    term: str
    source_sentence: str
    category: Literal["tool", "language", "framework", "domain", "methodology", "soft_skill"]
    tier: Literal["must_have", "nice_to_have"]
    reason: str
    present_in_resume: bool = False


class RoleContext(BaseModel):
    career_level: Literal["junior", "mid", "senior", "staff"]
    needs_ml_framing: bool = False
    primary_domain: str = ""


class KeywordExtractionOutput(BaseModel):
    must_have_keywords: list[Keyword] = []
    nice_to_have_keywords: list[Keyword] = []
    action_verbs: list[str] = []
    seniority_signals: list[str] = []
    boolean_search_terms: list[str] = []
    role_context: RoleContext = RoleContext(career_level="mid")
    # Deterministic tonal fingerprint of the JD; feeds Phase 3 wording
    # guidance and Phase 4's tone-alignment axis.  Defaults to a neutral
    # profile so existing sessions and fixtures remain compatible.
    tone_profile: JDToneProfile = JDToneProfile()


class KeywordStringsOutput(BaseModel):
    """Minimal schema for fallback keyword extraction when full output is hollow."""

    must_have_keywords: list[str] = []
    nice_to_have_keywords: list[str] = []
    action_verbs: list[str] = []
    seniority_signals: list[str] = []
