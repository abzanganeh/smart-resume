from __future__ import annotations

import asyncio
import json
from pathlib import Path

import structlog

from app.llm.base import LLMClient, LLMMessage
from app.llm.context import truncate_to_fit
from app.llm.structured import complete_structured
from app.models.audit import AuditLLMOutput, AuditOutput, BulletIssue, KeywordCoverage
from app.models.session import Session
from pydantic import BaseModel

log = structlog.get_logger()

_SYSTEM_BASE = (Path(__file__).parent / "prompts" / "system_base.txt").read_text()
_PHASE2 = (Path(__file__).parent / "prompts" / "phase2.txt").read_text()


def _keyword_coverage_from_phase1(session: Session) -> KeywordCoverage:
    p1 = session.phase1_output
    if p1 is None:
        return KeywordCoverage()

    claimed = set(session.user_claimed_keywords)
    present: list[str] = []
    missing_must: list[str] = []
    missing_nice: list[str] = []

    for kw in p1.must_have_keywords:
        if kw.present_in_resume or kw.term in claimed:
            present.append(kw.term)
        else:
            missing_must.append(kw.term)
    for kw in p1.nice_to_have_keywords:
        if kw.present_in_resume or kw.term in claimed:
            if kw.term not in present:
                present.append(kw.term)
        else:
            missing_nice.append(kw.term)

    return KeywordCoverage(
        present=present,
        missing_must_have=missing_must,
        missing_nice_to_have=missing_nice,
    )


def _compact_keyword_context(session: Session) -> str:
    p1 = session.phase1_output
    if p1 is None:
        return ""

    claimed = set(session.user_claimed_keywords)
    lines = ["KEYWORDS FROM PHASE 1 (use these lists; do not re-extract):"]

    for kw in p1.must_have_keywords:
        status = "present" if (kw.present_in_resume or kw.term in claimed) else "MISSING"
        lines.append(f"  [must-have] {kw.term} — {status}")

    for kw in p1.nice_to_have_keywords:
        status = "present" if (kw.present_in_resume or kw.term in claimed) else "missing"
        lines.append(f"  [nice-to-have] {kw.term} — {status}")

    return "\n".join(lines)


def _score_from_phase1(session: Session, coverage: KeywordCoverage) -> int:
    p1 = session.phase1_output
    if not p1 or not p1.must_have_keywords:
        return 50
    must_total = len(p1.must_have_keywords)
    must_missing = len(coverage.missing_must_have)
    must_ratio = (must_total - must_missing) / must_total
    return max(15, min(95, int(35 + must_ratio * 60)))


def _llm_audit_is_hollow(output: AuditLLMOutput) -> bool:
    return (
        output.overall_score == 0
        and not (output.summary or "").strip()
        and not output.bullet_issues
        and not output.cliches_found
        and not output.contact_issues
    )


def _reject_hollow_llm(output: BaseModel) -> str | None:
    if not isinstance(output, AuditLLMOutput):
        return None
    if _llm_audit_is_hollow(output):
        return (
            "Your JSON parsed but is empty. Return overall_score (1-100), a summary string, "
            "and bullet_issues for weak resume bullets. Do not return all-empty arrays."
        )
    if output.overall_score == 0:
        return "overall_score must be between 1 and 100 based on audit findings."
    if not (output.summary or "").strip():
        return "summary must be a non-empty string describing the main audit findings."
    return None


_MAX_BULLET_ISSUES = 10
_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


def _bullet_issue_priority(issue: BulletIssue) -> int:
    """Higher = more important to fix for this JD."""
    score = _SEVERITY_RANK.get(issue.severity, 1)
    score += len(issue.missing_keywords) * 3
    flags = set(issue.issues or [])
    if "irrelevant" in flags:
        return -100
    if "missing_keyword" in flags:
        score += 4
    if "no_metric" in flags:
        score += 1
    if "no_action_verb" in flags:
        score += 1
    if "cliche" in flags:
        score += 1
    return score


def _prioritize_bullet_issues(issues: list[BulletIssue]) -> list[BulletIssue]:
    """Keep JD-relevant, high-impact bullets only."""
    ranked = sorted(issues, key=_bullet_issue_priority, reverse=True)
    kept = [issue for issue in ranked if _bullet_issue_priority(issue) > 0]
    return kept[:_MAX_BULLET_ISSUES]


def _merge_audit(coverage: KeywordCoverage, llm: AuditLLMOutput) -> AuditOutput:
    return AuditOutput(
        keyword_coverage=coverage,
        bullet_issues=_prioritize_bullet_issues(llm.bullet_issues),
        cliches_found=llm.cliches_found,
        irrelevant_sections=llm.irrelevant_sections,
        page_estimate=llm.page_estimate,
        page_limit_exceeded=llm.page_limit_exceeded,
        contact_issues=llm.contact_issues,
        overall_score=llm.overall_score,
        summary=llm.summary,
    )


async def run(
    session: Session,
    llm: LLMClient,
    event_queue: asyncio.Queue,
) -> AuditOutput:
    await event_queue.put({"event": "progress", "phase": 2, "message": "Scanning resume for missing ATS keywords…"})
    await event_queue.put({"event": "progress", "phase": 2, "message": "Checking every bullet for action verbs and measurable impact…"})
    await event_queue.put({"event": "progress", "phase": 2, "message": "Scoring audit results against keyword coverage and quality rules…"})

    if not session.phase1_output:
        raise RuntimeError("Phase 1 must complete before Phase 2.")

    coverage = _keyword_coverage_from_phase1(session)
    resume_text = session.resume_raw or ""
    jd_text = session.jd_raw or ""
    resume_text, jd_text = truncate_to_fit(llm, resume_text, jd_text)
    career_stage = session.user_info.career_stage if session.user_info else "mid"
    keyword_context = _compact_keyword_context(session)

    claimed_section = ""
    if session.user_claimed_keywords:
        kw_list = ", ".join(session.user_claimed_keywords)
        claimed_section = (
            f"\nCANDIDATE-CONFIRMED SKILLS (treat as present in resume):\n{kw_list}\n"
        )
    if session.user_extra_notes.strip():
        claimed_section += f"\nADDITIONAL CANDIDATE CONTEXT:\n{session.user_extra_notes.strip()}\n"

    messages = [
        LLMMessage(role="system", content=_SYSTEM_BASE + "\n\n" + _PHASE2),
        LLMMessage(
            role="user",
            content=(
                f"CAREER STAGE: {career_stage}\n"
                f"{claimed_section}\n"
                f"{keyword_context}\n\n"
                f"JOB DESCRIPTION:\n{jd_text}\n\n"
                f"CANDIDATE'S RESUME:\n{resume_text}\n\n"
                "Do NOT output keyword_coverage — it is pre-computed. "
                "Return bullet_issues, cliches_found, page_estimate, contact_issues, overall_score, and summary."
            ),
        ),
    ]

    llm_output: AuditLLMOutput | None = None
    try:
        llm_output = await complete_structured(
            llm,
            messages,
            AuditLLMOutput,
            max_tokens=8192,
            max_retries=2,
            accept_result=_reject_hollow_llm,
        )
    except Exception as exc:
        log.warning("phase2_llm_failed_using_fallback", error=str(exc))
        llm_output = None

    if llm_output is None or _llm_audit_is_hollow(llm_output):
        fallback_score = _score_from_phase1(session, coverage)
        must = len(coverage.missing_must_have)
        present = len(coverage.present)
        llm_output = AuditLLMOutput(
            overall_score=fallback_score,
            summary=(
                f"Keyword scan: {present} JD keywords found in resume, {must} must-have gaps remain. "
                "Bullet-level audit could not be completed — retry for the full analysis."
            ),
            page_estimate="1 page" if len(resume_text) < 3000 else "2 pages",
        )

    output = _merge_audit(coverage, llm_output)
    await event_queue.put({"event": "progress", "phase": 2, "message": f"Finalizing audit — audit score {output.overall_score}/100…"})
    await event_queue.put({"event": "partial", "phase": 2, "data": json.loads(output.model_dump_json())})
    log.info("phase2_done", overall_score=output.overall_score, issues=len(output.bullet_issues))
    return output
