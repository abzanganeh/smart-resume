from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator import run_phase
from app.agent.phase3_postprocess import normalize_skills_to_categories
from app.config import settings, should_skip_billing_quota
from app.db.engine import get_db
from app.llm.factory import get_llm_client
from app.limiter import limiter
from app.models.audit import AuditOutput
from app.models.rewrite import ResumeVersion, TailoredExperienceEntry, TailoredResumeOutput
from app.models.session import PhaseRunScope, PhaseStatus
from app.models.user import User
from app.services.auth.tokens import (
    TokenExpiredError,
    TokenInvalidError,
    decode_access_token,
)
from app.services.billing.exceptions import (
    AccountSuspendedError,
    InsufficientCreditsError,
)
from app.services.billing.quota import (
    check_and_increment_quota,
    check_quota_for_section_regen,
    QuotaAction,
)
from app.services.billing.exceptions import PlanLimitReachedError, SubscriptionRequiredError
from app.services.master_resume.crud import has_any_live_chunk
from app.services.llm_session_config import apply_llm_request_headers
from app.services.session_store import (
    get_session,
    is_phase_lock_held,
    release_phase_lock,
    reset_phase,
    update_session,
)

MAX_PHASE3_VERSIONS = 20


def _cached_output_replayable(session, phase: int) -> bool:
    output = getattr(session, f"phase{phase}_output", None)
    if output is None:
        return False
    if phase == 1:
        return bool(output.must_have_keywords or output.nice_to_have_keywords)
    if phase == 2:
        return not (
            output.overall_score == 0
            and not (output.summary or "").strip()
            and not output.bullet_issues
            and not output.keyword_coverage.missing_must_have
        )
    return True


def _append_version_snapshot(
    session,
    *,
    label: str,
    output: TailoredResumeOutput,
) -> ResumeVersion:
    if len(session.phase3_versions) >= MAX_PHASE3_VERSIONS:
        session.phase3_versions.pop(0)
    version_num = len(session.phase3_versions) + 1
    snapshot_id = str(uuid.uuid4())[:8]
    version = ResumeVersion(
        version=version_num,
        snapshot_id=snapshot_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        label=label,
        output=output,
    )
    session.phase3_versions.append(version)
    return version


def _versions_payload(session) -> list[dict]:
    return [
        {
            "version": v.version,
            "snapshot_id": v.snapshot_id,
            "created_at": v.created_at,
            "label": v.label,
        }
        for v in session.phase3_versions
    ]


async def _resolve_bearer_user_id(
    authorization: str | None,
    session,
) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return session.user_id
    token = authorization[7:].strip()
    if not token:
        return session.user_id
    try:
        claims = decode_access_token(token, expected_type="access")
        bearer_sub = str(claims.get("sub") or "")
        if not bearer_sub:
            return session.user_id
        if session.user_id and session.user_id != bearer_sub:
            raise HTTPException(
                status_code=403,
                detail="Session does not belong to this user.",
            )
        if session.user_id != bearer_sub:
            session.user_id = bearer_sub
            await update_session(session)
        return bearer_sub
    except (TokenExpiredError, TokenInvalidError):
        return session.user_id


router = APIRouter(prefix="/api/sessions", tags=["phases"])


class RunPhaseRequest(BaseModel):
    force: bool = False
    scope: PhaseRunScope | None = None
    # Step 19/20: user-selected LLM tier for Phase 3.  Ignored for
    # other phases.  The orchestrator falls back to "standard" when
    # the user is not entitled to the requested tier.
    llm_tier: Literal["standard", "better", "best"] | None = None


@router.post("/{session_id}/phases/{phase}/run", status_code=202)
@limiter.limit("10/minute")
async def trigger_phase(
    request: Request,
    session_id: str,
    phase: int,
    body: RunPhaseRequest = RunPhaseRequest(),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_provider: str | None = Header(default=None, alias="X-Provider"),
    x_model: str | None = Header(default=None, alias="X-Model"),
    db: AsyncSession = Depends(get_db),
):
    if phase not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="Phase must be 1, 2, 3, or 4.")

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    user_id = await _resolve_bearer_user_id(authorization, session)

    if phase >= 2 and getattr(session, f"phase{phase - 1}_status") != PhaseStatus.done:
        raise HTTPException(
            status_code=422,
            detail=f"Phase {phase - 1} must complete before starting Phase {phase}.",
        )

    if body.scope is not None and phase != 3:
        raise HTTPException(status_code=422, detail="Scoped runs are only supported for Phase 3.")

    if body.scope is not None and session.phase3_status != PhaseStatus.done:
        raise HTTPException(
            status_code=422,
            detail="Phase 3 must complete before a scoped regeneration.",
        )

    # Force runs always win — explicitly clear stale state before the lock check
    # so the user can recover from a phase that crashed mid-run (e.g. backend
    # restart left status="running" and the Redis lock orphaned).
    if body.force:
        await reset_phase(session_id, phase)
        session = await get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

    phase_status = getattr(session, f"phase{phase}_status")
    if phase_status == PhaseStatus.running:
        # Self-heal: if Redis no longer holds the lock, the previous run
        # died without releasing it. Treat the running flag as stale.
        if not await is_phase_lock_held(session_id, phase):
            await reset_phase(session_id, phase)
            session = await get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
        else:
            raise HTTPException(
                status_code=409, detail=f"Phase {phase} is already running."
            )

    # Master resume is optional — Phase 3 runs with the session resume when
    # no chunks are present, so we no longer block here. The retrieval
    # service handles zero-chunk gracefully by skipping the retrieval step.

    if body.scope is not None and user_id and not should_skip_billing_quota():
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            uid = None
        if uid is not None:
            user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
            if user is not None:
                try:
                    await check_quota_for_section_regen(
                        db, user=user, session_id=session_id
                    )
                    await db.commit()
                except AccountSuspendedError:
                    raise HTTPException(status_code=403, detail={"code": "account_suspended"})
                except InsufficientCreditsError:
                    raise HTTPException(
                        status_code=402,
                        detail={
                            "code": "insufficient_credits",
                            "message": "You're out of credits. Section regeneration costs 1 credit.",
                        },
                    )

    # Phase 4 is an ATS recalculation — charge 1 credit / plan counter slot.
    if phase == 4 and user_id and not should_skip_billing_quota():
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            uid = None
        if uid is not None:
            user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
            if user is not None:
                try:
                    await check_and_increment_quota(
                        db,
                        user=user,
                        action=QuotaAction.ats_recalc,
                        session_id=session_id,
                    )
                    await db.commit()
                except AccountSuspendedError:
                    raise HTTPException(status_code=403, detail={"code": "account_suspended"})
                except (InsufficientCreditsError, PlanLimitReachedError, SubscriptionRequiredError) as exc:
                    raise HTTPException(
                        status_code=402,
                        detail={
                            "code": "insufficient_credits",
                            "action": "ats_recalc",
                            "message": "You're out of credits. ATS score recalculation costs 1 credit.",
                        },
                    ) from exc

    apply_llm_request_headers(
        session,
        x_provider=x_provider,
        x_model=x_model,
    )
    await update_session(session)

    session.phase_run_requested = phase
    session.phase_run_scope = body.scope
    if phase == 3 and body.llm_tier is not None:
        session.phase3_llm_tier = body.llm_tier
    await update_session(session)

    return {
        "job_id": f"phase{phase}-{session_id[:8]}",
        "stream_url": f"/api/sessions/{session_id}/phases/{phase}/events",
    }


@router.get("/{session_id}/phases/{phase}/events")
async def phase_events(session_id: str, phase: int):
    """SSE stream. Triggers the phase and streams events to the client."""
    if phase not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="Phase must be 1, 2, 3, or 4.")

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    phase_status = getattr(session, f"phase{phase}_status")
    run_requested = session.phase_run_requested == phase

    if (
        phase_status == PhaseStatus.done
        and not run_requested
        and _cached_output_replayable(session, phase)
    ):
        output = getattr(session, f"phase{phase}_output")
        if output is not None:

            async def replay():
                payload = json.dumps({
                    "event": "done",
                    "phase": phase,
                    "output": json.loads(output.model_dump_json()),
                })
                yield f"data: {payload}\n\n"
                yield 'data: {"event": "stream_end"}\n\n'

            return StreamingResponse(replay(), media_type="text/event-stream")

    if run_requested:
        session.phase_run_requested = None
        await update_session(session)

    event_queue: asyncio.Queue = asyncio.Queue()
    llm = get_llm_client(session.provider, session.model)

    task = asyncio.create_task(run_phase(session_id, phase, llm, event_queue))

    async def event_generator():
        sentinel = object()
        while True:
            try:
                from app.config import settings as _settings

                item = await asyncio.wait_for(
                    event_queue.get(), timeout=_settings.SSE_KEEPALIVE_SECONDS
                )
            except asyncio.TimeoutError:
                yield "data: {\"event\": \"keepalive\"}\n\n"
                continue

            if item is sentinel:
                break

            yield f"data: {json.dumps(item)}\n\n"

            if item.get("event") in ("done", "error"):
                break

        yield "data: {\"event\": \"stream_end\"}\n\n"

    async def run_and_signal():
        try:
            await task
        finally:
            await event_queue.put(object())

    asyncio.create_task(run_and_signal())
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class TailoredInlinePatch(BaseModel):
    section_id: str
    content: str | dict | list
    undo_token: str | None = None


class AuditPatchRequest(BaseModel):
    output: AuditOutput | None = None
    summary: str | None = None
    overall_score: int | None = Field(default=None, ge=0, le=100)


async def _apply_audit_patch(session_id: str, body: AuditPatchRequest):
    """Persist manual Phase 2 edits and mark downstream phases stale."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.phase2_output:
        raise HTTPException(status_code=422, detail="No audit output exists yet.")

    audit = session.phase2_output
    if body.output is not None:
        audit = body.output
    else:
        if body.summary is not None:
            audit.summary = body.summary
        if body.overall_score is not None:
            audit.overall_score = body.overall_score

    session.phase2_output = audit
    now = datetime.now(timezone.utc)
    session.stale_since = now
    session.phase3_stale_since = now
    session.phase4_stale_since = now
    await update_session(session)

    return {
        "ok": True,
        "stale": {
            "3": session.phase3_stale_since.isoformat(),
            "4": session.phase4_stale_since.isoformat(),
        },
    }


@router.patch("/{session_id}/audit")
async def patch_audit_output(session_id: str, body: AuditPatchRequest):
    return await _apply_audit_patch(session_id, body)


@router.post("/{session_id}/audit")
async def post_audit_output(session_id: str, body: AuditPatchRequest):
    """Alias for clients using POST to save manual Phase 2 edits."""
    return await _apply_audit_patch(session_id, body)


def _maybe_embed_edited_bullet(session: "Session", body: dict) -> None:  # type: ignore[name-defined]
    """Fire-and-forget: embed an accepted experience bullet into the corpus.

    Only embeds when the edit targets a single named experience bullet
    and the session has an authenticated user.  Skips silently on any
    missing context so the response is never blocked.
    """
    if not settings.DATABASE_URL.strip():
        return

    user_id_str = getattr(session, "user_id", None)
    if not user_id_str:
        return

    section = body.get("section") or (
        # section_id path: e.g. "experience:Acme Corp"
        body.get("section_id", "").split(":")[0]
        if "section_id" in body
        else ""
    )
    if section != "experience":
        return

    new_text = (body.get("new_text") or body.get("content") or "").strip()
    if not new_text:
        return

    company = body.get("company") or (
        body.get("section_id", "").split(":", 1)[1]
        if ":" in body.get("section_id", "")
        else None
    )
    bullet_index = body.get("bullet_index")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        return

    from app.services.corpus_writer import embed_bullet_fix

    asyncio.create_task(
        embed_bullet_fix(
            user_id=user_id,
            session_id=session.session_id,
            bullet_text=new_text,
            company=company,
            bullet_index=bullet_index,
            section_type="experience",
        ),
        name=f"corpus_bullet:{session.session_id}",
    )


@router.patch("/{session_id}/resume/tailored")
async def patch_tailored_resume(session_id: str, body: dict):
    """Save inline edits; supports legacy field patches and section_id updates."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.phase3_output:
        raise HTTPException(status_code=422, detail="No tailored resume exists yet.")

    output = session.phase3_output
    label = "User edit"
    skills_edited = False

    if "section_id" in body:
        section_id = str(body["section_id"])
        content = body.get("content", "")
        label = f"Inline edit: {section_id}"

        if section_id == "summary":
            output.summary = str(content)
        elif section_id == "contact":
            contact = dict(output.contact or {})
            contact["name"] = str(content).strip()
            output.contact = contact
            label = "User edit: contact/name"
        elif section_id == "skills":
            output.skills = list(content) if isinstance(content, list) else output.skills
            skills_edited = True
        elif section_id.startswith("experience:"):
            company = section_id.split(":", 1)[1]
            for entry in output.experience:
                if entry.company == company:
                    if isinstance(content, list):
                        entry.bullets = [str(b) for b in content]
                    else:
                        idx = body.get("bullet_index")
                        if idx is not None and idx < len(entry.bullets):
                            entry.bullets[idx] = str(content)
                    break
        elif section_id.startswith("education:"):
            institution = section_id.split(":", 1)[1]
            for entry in output.education:
                if entry.institution == institution:
                    if isinstance(content, list):
                        entry.bullets = [str(b) for b in content]
                    else:
                        entry.degree = str(content)
                    break
        elif section_id == "add_section" and isinstance(content, dict):
            section = content.get("section", "experience")
            text = str(content.get("text", ""))
            if section == "experience":
                output.experience.append(
                    TailoredExperienceEntry(
                        title=str(content.get("title", "Experience")),
                        company=str(content.get("company", "Manual entry")),
                        dates=str(content.get("dates", "")),
                        bullets=[text] if text else [],
                    )
                )
            elif section == "projects":
                output.projects.append(
                    {
                        "name": str(content.get("title", "Project")),
                        "description": str(content.get("company", "")),
                        "bullets": [text] if text else [],
                    }
                )
            elif section == "certifications":
                cert = text.strip() or str(content.get("title", "")).strip()
                if cert and cert not in output.certifications:
                    output.certifications.append(cert)
            label = f"Manual add: {section}"
    else:
        section = body.get("section")
        bullet_index = body.get("bullet_index")
        new_text = body.get("new_text", "")
        company = body.get("company")

        if section == "summary":
            output.summary = new_text
            label = "User edit: summary"
        elif section == "contact" and body.get("new_name") is not None:
            contact = dict(output.contact or {})
            contact["name"] = str(body["new_name"]).strip()
            output.contact = contact
            label = "User edit: contact/name"
        elif section == "experience" and company is not None and bullet_index is not None:
            for entry in output.experience:
                if entry.company != company:
                    continue
                bullets = list(entry.bullets)
                if bullet_index == len(bullets):
                    bullets.append(new_text)
                elif bullet_index < len(bullets):
                    if str(new_text).strip():
                        bullets[bullet_index] = new_text
                    else:
                        bullets.pop(bullet_index)
                entry.bullets = bullets
                break
            label = f"User edit: experience/{company}"
        elif section == "experience" and company is not None and body.get("new_title") is not None:
            new_title = str(body["new_title"]).strip()
            for entry in output.experience:
                if entry.company != company:
                    continue
                entry.title = new_title
                break
            label = f"User edit: experience/{company}/title"
        elif section == "experience" and company is not None and body.get("new_company") is not None:
            new_company = str(body["new_company"]).strip()
            for entry in output.experience:
                if entry.company == company:
                    entry.company = new_company
                    break
            label = f"User edit: experience/{company}/company"
        elif section == "experience" and company is not None and body.get("new_dates") is not None:
            new_dates = str(body["new_dates"]).strip()
            for entry in output.experience:
                if entry.company == company:
                    entry.dates = new_dates
                    break
            label = f"User edit: experience/{company}/dates"
        elif section == "experience" and body.get("delete") is True:
            exp_index = body.get("experience_index")
            if exp_index is not None:
                idx = int(exp_index)
                if 0 <= idx < len(output.experience):
                    output.experience.pop(idx)
                    label = f"User edit: experience/delete/{idx}"
            elif company is not None:
                for i, entry in enumerate(output.experience):
                    if entry.company == company:
                        output.experience.pop(i)
                        label = f"User edit: experience/delete/{company}"
                        break
        elif section == "skills":
            output.skills = body.get("skills", output.skills)
            skills_edited = True
            label = "User edit: skills"
        elif section == "education" and bullet_index is not None:
            institution = body.get("institution")
            for entry in output.education:
                if entry.institution == institution:
                    bullets = list(entry.bullets)
                    if bullet_index == len(bullets):
                        bullets.append(new_text)
                    elif bullet_index < len(bullets):
                        if new_text.strip():
                            bullets[bullet_index] = new_text
                        else:
                            bullets.pop(bullet_index)
                    entry.bullets = bullets
                    break
            label = f"User edit: education/{institution}"
        elif section == "education_bullets":
            institution = body.get("institution")
            for entry in output.education:
                if entry.institution == institution:
                    entry.bullets = body.get("bullets", entry.bullets)
                    break
            label = f"User edit: education/{institution}"
        elif section == "education" and body.get("institution") is not None:
            institution = str(body["institution"])
            for entry in output.education:
                if entry.institution != institution:
                    continue
                if body.get("new_institution") is not None:
                    entry.institution = str(body["new_institution"]).strip()
                if body.get("new_degree") is not None:
                    entry.degree = str(body["new_degree"]).strip()
                if body.get("new_year") is not None:
                    entry.year = str(body["new_year"]).strip()
                break
            label = f"User edit: education/{institution}"
        elif section == "certifications" and body.get("delete") is True:
            cert_index = body.get("cert_index")
            if cert_index is not None:
                idx = int(cert_index)
                if 0 <= idx < len(output.certifications):
                    output.certifications.pop(idx)
                    label = f"User edit: certifications/delete/{idx}"
        elif section == "projects":
            project_index = body.get("project_index")
            if body.get("delete") is True and project_index is not None:
                idx = int(project_index)
                if 0 <= idx < len(output.projects):
                    output.projects.pop(idx)
                label = f"User edit: projects/delete/{project_index}"
            elif body.get("add_project") is not None:
                output.projects.append(body["add_project"])
                label = "User edit: projects/add"
            elif project_index is not None:
                idx = int(project_index)
                if 0 <= idx < len(output.projects):
                    raw = output.projects[idx]
                    proj = dict(raw) if isinstance(raw, dict) else {}
                    if body.get("new_name") is not None:
                        proj["name"] = str(body["new_name"]).strip()
                    if body.get("new_description") is not None:
                        proj["description"] = str(body["new_description"]).strip()
                    bullet_index = body.get("bullet_index")
                    if bullet_index is not None:
                        bullets = list(proj.get("bullets") or [])
                        bi = int(bullet_index)
                        new_text = str(body.get("new_text", ""))
                        if bi == len(bullets):
                            if new_text.strip():
                                bullets.append(new_text)
                        elif bi < len(bullets):
                            if new_text.strip():
                                bullets[bi] = new_text
                            else:
                                bullets.pop(bi)
                        proj["bullets"] = bullets
                    output.projects[idx] = proj
                label = f"User edit: projects/{project_index}"

    if skills_edited:
        must_have = (
            [k.term for k in session.phase1_output.must_have_keywords]
            if session.phase1_output
            else None
        )
        output.skills = normalize_skills_to_categories(output.skills, must_have)

    version = _append_version_snapshot(session, label=label, output=output)
    session.phase3_output = output
    now = datetime.now(timezone.utc)
    session.stale_since = now
    session.phase4_stale_since = now
    await update_session(session)

    # Embed the edited bullet into the corpus so future sessions can
    # retrieve it.  Only experience bullets carry enough signal — summary
    # and skills are too session-specific to be useful in cross-session RAG.
    _maybe_embed_edited_bullet(session, body)

    return {
        "version": version.version,
        "snapshot_id": version.snapshot_id,
        "phase3_versions": _versions_payload(session),
        "stale": {
            "4": session.phase4_stale_since.isoformat() if session.phase4_stale_since else None,
        },
    }


@router.get("/{session_id}/resume/versions")
async def get_versions(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"versions": _versions_payload(session)}


@router.post("/{session_id}/resume/versions/{snapshot_id}/restore")
async def restore_version(session_id: str, snapshot_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    match = next(
        (v for v in session.phase3_versions if v.snapshot_id == snapshot_id),
        None,
    )
    if not match:
        raise HTTPException(status_code=404, detail="Version not found")
    restored = _append_version_snapshot(
        session,
        label=f"Restored from v{match.version}",
        output=match.output,
    )
    session.phase3_output = match.output
    now = datetime.now(timezone.utc)
    session.stale_since = now
    session.phase4_stale_since = now
    await update_session(session)
    return {
        "version": restored.version,
        "snapshot_id": restored.snapshot_id,
        "tailored_output": match.output.model_dump(),
        "stale": {
            "4": session.phase4_stale_since.isoformat() if session.phase4_stale_since else None,
        },
    }
