"""Account export and closure routes (IMPLEMENTATION_PLAN §6)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from slowapi.util import get_remote_address
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import async_session_factory, get_db
from app.limiter import limiter
from app.models.export import ExportJob, ExportJobStatus
from app.models.export import ClosureRequest
from app.models.user import User
from app.services.auth.dependencies import get_current_user
from app.services.auth.tokens import decode_access_token
from app.services.export.assembler import process_export_job
from app.services.export.closure import cancel_closure, run_closure_tick, schedule_closure

log = structlog.get_logger("account.router")

router = APIRouter(prefix="/api/account", tags=["account"])

_scheduler_header = APIKeyHeader(name="X-Scheduler-Secret", auto_error=False)


def _rate_limit_user_key(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        try:
            claims = decode_access_token(token, expected_type="access")
            subject = str(claims.get("sub") or "").strip()
            if subject:
                return f"user:{subject}"
        except Exception:  # noqa: BLE001
            pass
        return f"token:{token[:64]}"
    return get_remote_address(request)


class ExportCreateResponse(BaseModel):
    job_id: uuid.UUID


class ExportJobResponse(BaseModel):
    id: uuid.UUID
    status: str
    presigned_url: str | None = None
    presigned_url_expires_at: datetime | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ExportListItem(BaseModel):
    id: uuid.UUID
    status: str
    presigned_url: str | None = None
    presigned_url_expires_at: datetime | None = None
    created_at: datetime
    completed_at: datetime | None = None


class CloseAccountRequest(BaseModel):
    cancel_subscription: bool = True


class CloseAccountResponse(BaseModel):
    ok: bool
    scheduled_delete_at: datetime


class ProfilePatchRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=200)


async def _run_export_background(job_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        try:
            await process_export_job(session, job_id)
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            log.error("export.background_failed", job_id=str(job_id), error=str(exc))


def _job_response(job: ExportJob) -> ExportJobResponse:
    return ExportJobResponse(
        id=job.id,
        status=job.status.value,
        presigned_url=job.presigned_url,
        presigned_url_expires_at=job.presigned_url_expires_at,
        error=job.error,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.patch("/profile")
@limiter.limit("30/minute")
async def patch_profile(
    request: Request,
    body: ProfilePatchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    user.display_name = body.display_name.strip()
    await db.flush()
    return {"ok": True, "display_name": user.display_name}


@router.post("/export", status_code=202)
@limiter.limit("2/day", key_func=_rate_limit_user_key)
async def create_export(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ExportCreateResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_count = (
        await db.execute(
            select(func.count())
            .select_from(ExportJob)
            .where(ExportJob.user_id == user.id)
            .where(ExportJob.created_at >= cutoff)
        )
    ).scalar_one()
    if recent_count >= 2:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "export_rate_limited", "limit": "2/24h"},
        )

    job = ExportJob(user_id=user.id, status=ExportJobStatus.pending)
    db.add(job)
    await db.flush()
    background_tasks.add_task(_run_export_background, job.id)
    return ExportCreateResponse(job_id=job.id)


@router.get("/export/{job_id}")
@limiter.limit("120/minute")
async def get_export(
    request: Request,
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ExportJobResponse:
    job = (
        await db.execute(
            select(ExportJob).where(
                ExportJob.id == job_id,
                ExportJob.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found")
    return _job_response(job)


@router.get("/exports")
@limiter.limit("30/minute")
async def list_exports(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[ExportListItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    rows = (
        await db.execute(
            select(ExportJob)
            .where(
                ExportJob.user_id == user.id,
                ExportJob.created_at >= cutoff,
            )
            .order_by(desc(ExportJob.created_at))
        )
    ).scalars().all()
    return [
        ExportListItem(
            id=j.id,
            status=j.status.value,
            presigned_url=j.presigned_url,
            presigned_url_expires_at=j.presigned_url_expires_at,
            created_at=j.created_at,
            completed_at=j.completed_at,
        )
        for j in rows
    ]


@router.post("/close")
@limiter.limit("5/day", key_func=_rate_limit_user_key)
async def close_account(
    request: Request,
    body: CloseAccountRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> CloseAccountResponse:
    if user.is_closure_pending:
        existing = (
            await db.execute(
                select(ClosureRequest).where(
                    ClosureRequest.user_id == user.id,
                    ClosureRequest.cancelled_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        scheduled = (
            existing.scheduled_delete_at
            if existing
            else user.closure_requested_at + timedelta(days=settings.ACCOUNT_CLOSURE_GRACE_DAYS)  # type: ignore[operator]
        )
        return CloseAccountResponse(ok=True, scheduled_delete_at=scheduled)

    row = await schedule_closure(
        db,
        user=user,
        cancel_subscription=body.cancel_subscription,
    )
    return CloseAccountResponse(ok=True, scheduled_delete_at=row.scheduled_delete_at)


@router.post("/close/cancel")
@limiter.limit("5/day", key_func=_rate_limit_user_key)
async def cancel_account_closure(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    ok = await cancel_closure(db, user=user)
    if not ok:
        raise HTTPException(status_code=404, detail="No pending closure request")
    return {"ok": True}


@router.delete("", status_code=200)
async def scheduler_delete_due_accounts(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_scheduler_secret: Annotated[str | None, Security(_scheduler_header)] = None,
) -> dict[str, Any]:
    """Internal endpoint for EventBridge closure tick."""
    secret = settings.INTERNAL_SCHEDULER_SECRET
    if not secret or x_scheduler_secret != secret:
        raise HTTPException(status_code=401, detail="Unauthorized")
    result = await run_closure_tick(db)
    return {
        "ok": True,
        "inspected": result.inspected,
        "deleted": [str(uid) for uid in result.deleted],
        "reminders_sent": result.reminders_sent,
    }


__all__ = ["router"]
