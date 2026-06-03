from __future__ import annotations

import asyncio
import json
import time
import uuid

import structlog

from app.db.engine import async_session_factory
from app.llm.base import LLMClient
from app.llm.factory import get_llm_client
from app.llm.pricing import estimate_cost, format_cost
from app.models.session import PhaseStatus, Session
from app.services import session_store
from app.services.billing.exceptions import InsufficientCreditsError
from app.services.billing.llm_upgrade import (
    Phase3RouteDecision,
    apply_phase3_tier,
)
from app.services.retrieval.exceptions import (
    MasterResumeRequiredError,
    PromptBudgetExceededError,
)

log = structlog.get_logger()


async def _resolve_phase3_llm(
    session: Session,
    fallback_llm: LLMClient,
    event_queue: asyncio.Queue,
) -> tuple[LLMClient, Phase3RouteDecision | None]:
    """Apply the Phase 3 tier middleware before the LLM call.

    - Resolves the effective tier from the user's entitlements
      (best subscription / better credits / standard fallback).
    - Atomically consumes a Better credit or increments
      ``Subscription.upgraded_resumes_used`` for Best subscribers.
    - On Best soft-cap hit (>=100 upgraded resumes) emits a
      ``best_soft_cap_hit`` SSE event and downgrades to Standard.
    - Builds a fresh LLM client targeting the resolved
      (provider, model_string) — never hardcoded — using the same
      BYOK key as the upstream client when present.

    Returns ``(llm, decision)``.  ``decision`` is None for anonymous
    demo sessions (no ``user_id``) so the legacy single-LLM path keeps
    working unchanged.
    """
    if session.user_id is None:
        return fallback_llm, None
    try:
        user_id = uuid.UUID(session.user_id)
    except ValueError:
        return fallback_llm, None

    requested = session.phase3_llm_tier or "standard"

    # BYOK respect: if the user supplied their own API key for the session
    # AND they did NOT explicitly upgrade to a premium tier, use their BYOK
    # provider/model. The tier system (Standard=platform Gemini, Better=…,
    # Best=Claude) is for users on platform-paid credits; BYOK users
    # already pay their LLM bill directly. Without this guard, an OpenAI
    # BYOK user on the default "standard" tier would silently route to
    # the platform's Gemini key (which may not even be configured).
    byok_key = (getattr(session, "byok_api_key", None) or "").strip()
    if requested == "standard" and byok_key and session.provider and session.model:
        return fallback_llm, None

    upgraded_llm: LLMClient | None = None
    async with async_session_factory() as db:
        try:
            decision = await apply_phase3_tier(
                db,
                user_id=user_id,
                requested_tier=requested,  # type: ignore[arg-type]
                session_id=session.session_id,
            )
            # Build the routed client before commit so any initialization
            # failure rolls back credit/counter side-effects.
            if not (
                decision.effective_tier == "standard"
                and decision.provider == fallback_llm.provider_name
                and decision.model_string == fallback_llm.model_name
            ):
                upgraded_llm = get_llm_client(
                    provider=decision.provider,
                    model=decision.model_string,
                    api_key=getattr(session, "byok_api_key", None),
                )
            await db.commit()
        except InsufficientCreditsError:
            await db.rollback()
            log.info(
                "phase3_tier_insufficient_credits",
                session_id=session.session_id,
                requested_tier=requested,
            )
            await event_queue.put({
                "event": "error",
                "phase": 3,
                "code": "insufficient_credits",
                "status": 402,
                "message": "Better LLM credit balance is empty.",
            })
            raise
        except Exception:
            await db.rollback()
            raise

    if decision.soft_cap_hit:
        await event_queue.put({
            "event": "best_soft_cap_hit",
            "phase": 3,
            "limit": 100,
            "message": (
                "Best LLM quota reached for this period — "
                "using Standard for the rest of the cycle."
            ),
        })
    elif decision.downgrade_reason is not None:
        await event_queue.put({
            "event": "tier_downgraded",
            "phase": 3,
            "reason": decision.downgrade_reason.value,
            "effective_tier": decision.effective_tier,
        })

    if upgraded_llm is None:
        return fallback_llm, decision

    log.info(
        "phase3_tier_routed",
        session_id=session.session_id,
        tier=decision.effective_tier,
        provider=decision.provider,
        model=decision.model_string,
    )
    await event_queue.put({
        "event": "tier_resolved",
        "phase": 3,
        "tier": decision.effective_tier,
        "provider": decision.provider,
        "model": decision.model_string,
    })
    return upgraded_llm, decision


def _classify_error(exc: BaseException) -> str:
    """Return a short machine-readable error class for the frontend."""
    msg = str(exc).lower()
    if any(k in msg for k in ("rate limit", "ratelimit", "429", "too many requests")):
        return "llm_rate_limit"
    if any(k in msg for k in ("timeout", "timed out", "read timeout", "connect timeout")):
        return "llm_timeout"
    if any(k in msg for k in ("api key", "apikey", "api_key", "unauthorized", "401", "403", "authentication")):
        return "llm_auth"
    if any(k in msg for k in ("context length", "context window", "token limit", "max tokens", "too long")):
        return "llm_context_length"
    if any(k in msg for k in ("invalid json", "json decode", "parse error", "jsondecodeerror", "failed to parse")):
        return "llm_parse_error"
    if any(k in msg for k in ("connection", "network", "connectionerror", "ssl")):
        return "llm_network"
    if any(k in msg for k in ("overloaded", "capacity", "503", "service unavailable")):
        return "llm_overloaded"
    return "phase_error"


def _user_facing_error(exc: BaseException) -> str:
    """Return a clean, user-facing error message for display in the UI."""
    kind = _classify_error(exc)
    messages = {
        "llm_rate_limit": (
            "The AI model hit its rate limit. Wait a moment and retry — "
            "this is a temporary quota on the LLM provider's side, not a platform issue."
        ),
        "llm_timeout": (
            "The AI model took too long to respond (timeout). "
            "The LLM provider may be under load. Please retry."
        ),
        "llm_auth": (
            "The AI model rejected the API key (authentication error). "
            "If you supplied your own key, please check it in Settings → BYOK."
        ),
        "llm_context_length": (
            "Your resume or job description is too long for this model's context window. "
            "Try shortening the job description or reducing resume length, then retry."
        ),
        "llm_parse_error": (
            "The AI model returned a response that could not be parsed. "
            "This is an LLM formatting issue — retrying usually resolves it."
        ),
        "llm_network": (
            "Could not reach the AI model (network error). "
            "Check your internet connection or try again shortly."
        ),
        "llm_overloaded": (
            "The AI model is temporarily overloaded. "
            "This is a provider-side issue — please wait a minute and retry."
        ),
    }
    return messages.get(kind, "The AI step encountered an error. Please retry.")


async def run_phase(
    session_id: str,
    phase: int,
    llm: LLMClient,
    event_queue: asyncio.Queue,
) -> None:
    """
    Run a single agent phase.
    Acquires the phase lock, executes the phase function, saves output, releases lock.
    Emits SSE events to event_queue throughout.
    """
    if not await session_store.acquire_phase_lock(session_id, phase):
        await event_queue.put({"event": "error", "phase": phase, "message": "Phase is already running."})
        raise RuntimeError(f"Phase {phase} is already running for session {session_id}")

    session = await session_store.get_session(session_id)
    if session is None:
        await event_queue.put({"event": "error", "phase": phase, "message": "Session not found."})
        await session_store.release_phase_lock(session_id, phase)
        return

    await session_store.update_phase_status(session_id, phase, PhaseStatus.running)
    await event_queue.put({"event": "progress", "phase": phase, "message": f"Phase {phase} starting…"})

    start = time.monotonic()
    try:
        from app.agent import phase1_keywords, phase2_audit, phase3_rewrite, phase4_qa

        match phase:
            case 1:
                output = await phase1_keywords.run(session, llm, event_queue)
            case 2:
                output = await phase2_audit.run(session, llm, event_queue)
            case 3:
                scope = session.phase_run_scope
                # Step 19 — resolve LLM tier (consume Better credit /
                # increment Best counter) before the rewrite call.
                phase3_llm, _ = await _resolve_phase3_llm(
                    session, llm, event_queue
                )
                output = await phase3_rewrite.run(
                    session, phase3_llm, event_queue, scope=scope
                )
            case 4:
                output = await phase4_qa.run(session, llm, event_queue)
            case _:
                raise ValueError(f"Unknown phase: {phase}")

        await session_store.save_phase_output(session_id, phase, output)

        # Fix 3 — when Phase 2 completes, mark downstream phases stale so the
        # user sees a warning dot on the Rewrite / QA tabs.  Only stale a phase
        # when its output already exists (phases that have never run stay clean).
        if phase == 2:
            session = await session_store.get_session(session_id)
            if session is not None:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                changed = False
                if session.phase3_output is not None:
                    session.phase3_stale_since = now
                    changed = True
                if session.phase4_output is not None:
                    session.phase4_stale_since = now
                    changed = True
                if changed:
                    await session_store.update_session(session)

        # Step 27 — persist ResumeRecord + ATS history after Phase 4.
        if phase == 4 and session.user_id:
            try:
                user_id = uuid.UUID(session.user_id)
                from app.services.dashboard.resume_record import (
                    upsert_resume_record_from_session,
                )

                persisted = await session_store.get_session(session_id)
                if persisted is not None:
                    async with async_session_factory() as db:
                        await upsert_resume_record_from_session(
                            db,
                            user_id=user_id,
                            session=persisted,
                            ats_score=output.ats_score,
                        )
                        await db.commit()
            except Exception as exc:  # noqa: BLE001 — do not fail the phase run
                log.warning(
                    "resume_record_upsert_failed",
                    session_id=session_id,
                    error=str(exc),
                )

        # Clear stale markers after a successful phase run (§18.6).
        session = await session_store.get_session(session_id)
        if session is not None:
            if phase == 3:
                session.phase3_stale_since = None
                session.phase4_stale_since = None
                session.phase_run_scope = None
                # Reset the LLM tier hint so the next run requires an
                # explicit selection (no implicit credit consumption).
                session.phase3_llm_tier = None
            elif phase == 4:
                session.phase4_stale_since = None
            await session_store.update_session(session)
        elapsed = round(time.monotonic() - start, 2)
        log.info("phase_complete", session_id=session_id, phase=phase, elapsed_s=elapsed,
                 provider=llm.provider_name, model=llm.model_name)
        await event_queue.put({
            "event": "done",
            "phase": phase,
            "output": json.loads(output.model_dump_json()),
        })

    except MasterResumeRequiredError as e:
        # IMPLEMENTATION_PLAN §6a — surface 409 so the frontend can route
        # the user to /profile.  Keep the phase status as ``pending`` so
        # they can rerun once a master resume has been uploaded.
        await session_store.update_phase_status(session_id, phase, PhaseStatus.pending)
        log.info("phase_blocked_master_resume_required", session_id=session_id, phase=phase)
        await event_queue.put({
            "event": "error",
            "phase": phase,
            "code": e.code,
            "status": 409,
            "message": str(e),
        })
        raise
    except PromptBudgetExceededError as e:
        await session_store.update_phase_status(session_id, phase, PhaseStatus.error)
        log.warning(
            "phase_prompt_budget_exceeded",
            session_id=session_id,
            phase=phase,
            total_tokens=e.total_tokens,
            budget=e.budget,
            model=e.model,
        )
        await event_queue.put({
            "event": "error",
            "phase": phase,
            "code": e.code,
            "status": 422,
            "message": str(e),
            "total_tokens": e.total_tokens,
            "budget": e.budget,
            "model": e.model,
        })
        raise
    except Exception as e:
        await session_store.update_phase_status(session_id, phase, PhaseStatus.error)
        log.error("phase_error", session_id=session_id, phase=phase, error=str(e))
        await event_queue.put({
            "event": "error",
            "phase": phase,
            "message": _user_facing_error(e),
            "debug": str(e),
            "error_type": _classify_error(e),
        })
        raise
    finally:
        await session_store.release_phase_lock(session_id, phase)
