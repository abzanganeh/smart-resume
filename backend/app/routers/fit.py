from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import job_fit as job_fit_agent
from app.config import settings
from app.db.engine import get_db
from app.llm.factory import get_llm_client
from app.limiter import limiter, rate_limit_key
from app.models.fit import FitAnalysisOutput
from app.models.fit_analysis import FitAnalysis
from app.models.billing import Subscription, SubscriptionStatus
from app.models.user import User
from app.parsers.docx_parser import extract_text_from_docx
from app.parsers.pdf_parser import extract_text_from_pdf
from app.parsers.text_parser import extract_text_from_txt
from app.services.auth.dependencies import get_current_user
from app.services.billing.exceptions import (
    AccountSuspendedError,
    PlanLimitReachedError,
    SubscriptionRequiredError,
)
from app.services.billing.quota import QuotaAction, check_and_increment_quota
from app.services.retrieval.exceptions import MasterResumeRequiredError
from app.services.auth.tokens import decode_access_token

router = APIRouter(prefix="/api/fit", tags=["fit"])
log = structlog.get_logger("fit.router")

_fit_locks: set[str] = set()

ALLOWED_JD_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


def _rate_limit_user_key(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        try:
            claims = decode_access_token(token, expected_type="access")
            subject = str(claims.get("sub") or "").strip()
            if subject:
                return f"user:{subject}"
        except Exception:  # noqa: BLE001 - fallback to token-prefix/IP keying
            pass
        return f"token:{token[:64]}"
    return rate_limit_key(request)


async def _fetch_jd_from_url(url: str) -> str:
    from app.parsers.html_parser import strip_html_to_text
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; TalioCV/1.0)"},
            )
            resp.raise_for_status()
            return strip_html_to_text(resp.text, max_chars=settings.MAX_JD_CHARS)
    except Exception as exc:
        log.warning("fit.jd_fetch_failed", url=url, error=str(exc))
        raise HTTPException(status_code=422, detail="Could not fetch JD from URL.") from exc


async def _extract_jd_text(
    *,
    jd_text: str | None,
    jd_url: str | None,
    file: UploadFile | None,
) -> str:
    text = (jd_text or "").strip()

    if file is not None:
        content_type = (file.content_type or "").lower()
        if content_type not in ALLOWED_JD_MIME:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported file type: {content_type or 'unknown'}",
            )
        file_bytes = await file.read()
        if len(file_bytes) > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=422,
                detail=f"File exceeds {settings.MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit.",
            )
        if "pdf" in content_type:
            text = extract_text_from_pdf(file_bytes)
        elif "wordprocessingml" in content_type:
            text = extract_text_from_docx(file_bytes)
        else:
            text = extract_text_from_txt(file_bytes)

    if jd_url and not text:
        text = await _fetch_jd_from_url(jd_url)

    text = text.strip()
    if not text:
        raise HTTPException(
            status_code=422,
            detail="Job description is empty — paste text, upload a file, or provide a URL.",
        )
    if len(text) > settings.MAX_JD_CHARS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Job description exceeds {settings.MAX_JD_CHARS:,} characters. "
                "Paste only the requirements section."
            ),
        )
    return text


def _jd_hash(jd_text: str) -> str:
    return hashlib.sha256(jd_text.encode("utf-8")).hexdigest()


def _empty_fit_output() -> FitAnalysisOutput:
    return FitAnalysisOutput(
        overall_fit_score=0,
        fit_label="weak",
        section_fits=[],
        key_gaps=[],
        key_strengths=[],
        recommendation="No recommendation available.",
        should_apply=False,
        suggested_master_resume_edits=[],
    )


def _safe_fit_output(payload: object) -> FitAnalysisOutput:
    if isinstance(payload, dict):
        try:
            return FitAnalysisOutput.model_validate(payload)
        except Exception:  # noqa: BLE001 - fallback avoids 500 on malformed legacy rows
            return _empty_fit_output()
    return _empty_fit_output()


async def _require_fit_subscription(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    now = datetime.now(timezone.utc)
    sub = (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(
                Subscription.status.in_(
                    [
                        SubscriptionStatus.active,
                        SubscriptionStatus.trialing,
                        SubscriptionStatus.grace,
                        SubscriptionStatus.cancel_at_period_end,
                    ]
                )
            )
            .where(Subscription.period_start <= now)
            .where(Subscription.period_end >= now)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=402, detail={"code": "subscription_required"})


class FetchJdRequest(BaseModel):
    jd_url: str = Field(..., min_length=8, max_length=2048)


class FetchJdResponse(BaseModel):
    jd_text: str


class FitHistoryItem(BaseModel):
    id: str
    jd_hash: str
    overall_fit_score: int
    fit_label: str
    created_at: str


class FitHistoryResponse(BaseModel):
    items: list[FitHistoryItem]
    total: int
    page: int
    page_size: int


class FitDetailResponse(BaseModel):
    id: str
    jd_hash: str
    jd_text: str
    result: FitAnalysisOutput
    created_at: str


@router.post("/fetch-jd", response_model=FetchJdResponse)
@limiter.limit("30/minute")
async def fetch_jd(
    request: Request,
    body: FetchJdRequest,
    user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
):
    """Fetch JD text from a job posting URL (same logic as session JD submit)."""
    jd_text = await _fetch_jd_from_url(body.jd_url)
    return FetchJdResponse(jd_text=jd_text)


@router.post("/analyze")
@limiter.limit("20/hour", key_func=_rate_limit_user_key)
async def analyze_fit(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    jd_text: Annotated[str | None, Form()] = None,
    jd_url: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
):
    """Run job-fit analysis and stream progress via SSE."""
    lock_key = str(user.id)
    if lock_key in _fit_locks:
        raise HTTPException(status_code=409, detail="Fit analysis is already running.")

    try:
        resolved_jd = await _extract_jd_text(jd_text=jd_text, jd_url=jd_url, file=file)
    except HTTPException:
        raise

    try:
        await check_and_increment_quota(
            db, user=user, action=QuotaAction.fit_analysis
        )
    except AccountSuspendedError:
        raise HTTPException(status_code=403, detail={"code": "account_suspended"})
    except SubscriptionRequiredError:
        raise HTTPException(status_code=402, detail={"code": "subscription_required"})
    except PlanLimitReachedError as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "plan_limit_reached",
                "action": exc.action,
                "used": exc.used,
                "limit": exc.limit,
            },
        )

    llm = get_llm_client(
        job_fit_agent.FIT_LLM_PROVIDER,
        job_fit_agent.FIT_LLM_MODEL,
    )

    async def event_generator():
        _fit_locks.add(lock_key)
        event_queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()
        analysis_id = uuid.uuid4()

        async def run_and_signal():
            try:
                output = await job_fit_agent.run(
                    db,
                    user_id=user.id,
                    jd_text=resolved_jd,
                    llm=llm,
                    event_queue=event_queue,
                )
                row = FitAnalysis(
                    id=analysis_id,
                    user_id=user.id,
                    jd_hash=_jd_hash(resolved_jd),
                    jd_text=resolved_jd,
                    result_json=json.loads(output.model_dump_json()),
                )
                db.add(row)
                await db.commit()
                await event_queue.put({
                    "event": "done",
                    "analysis_id": str(analysis_id),
                    "jd_text": resolved_jd,
                    "output": json.loads(output.model_dump_json()),
                })
            except MasterResumeRequiredError:
                await db.rollback()
                await event_queue.put({
                    "event": "error",
                    "message": "Upload a master resume on /profile before running fit analysis.",
                    "code": "master_resume_required",
                })
            except Exception as exc:
                await db.rollback()
                log.exception("fit_analysis_failed", user_id=str(user.id), error=str(exc))
                await event_queue.put({
                    "event": "error",
                    "message": "Fit analysis failed. Please retry.",
                })
            finally:
                await event_queue.put(sentinel)

        task = asyncio.create_task(run_and_signal())

        try:
            while True:
                try:
                    item = await asyncio.wait_for(event_queue.get(), timeout=60)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'event': 'keepalive'})}\n\n"
                    continue

                if item is sentinel:
                    break

                yield f"data: {json.dumps(item)}\n\n"

                if item.get("event") in ("done", "error"):
                    break

            yield f"data: {json.dumps({'event': 'stream_end'})}\n\n"
            await task
        finally:
            _fit_locks.discard(lock_key)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/history", response_model=FitHistoryResponse)
@limiter.limit("120/minute")
async def fit_history(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    await _require_fit_subscription(db, user_id=user.id)

    offset = (page - 1) * page_size
    total = (
        await db.execute(
            select(func.count()).select_from(FitAnalysis).where(
                FitAnalysis.user_id == user.id
            )
        )
    ).scalar_one()

    rows = (
        await db.execute(
            select(FitAnalysis)
            .where(FitAnalysis.user_id == user.id)
            .order_by(FitAnalysis.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()

    items: list[FitHistoryItem] = []
    for row in rows:
        result = _safe_fit_output(row.result_json)
        items.append(
            FitHistoryItem(
                id=str(row.id),
                jd_hash=row.jd_hash,
                overall_fit_score=result.overall_fit_score,
                fit_label=result.fit_label,
                created_at=row.created_at.isoformat() if row.created_at else "",
            )
        )

    return FitHistoryResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/{analysis_id}", response_model=FitDetailResponse)
@limiter.limit("120/minute")
async def fit_detail(
    request: Request,
    analysis_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _require_fit_subscription(db, user_id=user.id)

    try:
        aid = uuid.UUID(analysis_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid analysis id.") from None

    row = (
        await db.execute(
            select(FitAnalysis).where(
                FitAnalysis.id == aid,
                FitAnalysis.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    return FitDetailResponse(
        id=str(row.id),
        jd_hash=row.jd_hash,
        jd_text=row.jd_text,
        result=_safe_fit_output(row.result_json),
        created_at=row.created_at.isoformat() if row.created_at else "",
    )
