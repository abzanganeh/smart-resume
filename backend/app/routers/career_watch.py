"""Career Watch API — watchlist and alerts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.models.career_watch import CareerAlert, CareerAlertStatus, CareerJobCache
from app.models.user import User
from app.services.auth.dependencies import get_current_user
from app.services.career_watch.limits import CareerWatchLimitError, get_career_watch_limits
from app.services.career_watch.notifications import dismiss_alert
from app.services.career_watch.watchlist import (
    WatchlistEntry,
    add_watch,
    detect_careers_page,
    list_watchlist,
    remove_watch,
    update_watch_keywords,
)

router = APIRouter(prefix="/api/career-watch", tags=["career-watch"])


class DetectRequest(BaseModel):
    careers_page_url: str = Field(..., min_length=8, max_length=2000)


class DetectResponse(BaseModel):
    ats_type: str
    board_token: str | None
    careers_page_url: str
    company_name: str | None


class WatchCreateRequest(BaseModel):
    careers_page_url: str = Field(..., min_length=8, max_length=2000)
    company_name: str | None = Field(None, max_length=500)
    keywords: list[str] = Field(default_factory=list, max_length=20)


class WatchUpdateRequest(BaseModel):
    keywords: list[str] = Field(..., max_length=20)


class WatchResponse(BaseModel):
    id: uuid.UUID
    watched_company_id: uuid.UUID
    company_name: str
    careers_page_url: str
    ats_type: str
    keywords: list[str]
    is_active: bool
    created_at: datetime


class LimitsResponse(BaseModel):
    max_companies: int
    poll_interval_minutes: int
    active_watches: int


class AlertResponse(BaseModel):
    id: uuid.UUID
    status: str
    match_score: float | None
    match_reason: str | None
    created_at: datetime
    notified_at: datetime | None
    job_title: str
    job_location: str
    apply_url: str


def _watch_response(entry: WatchlistEntry) -> WatchResponse:
    return WatchResponse(
        id=entry.id,
        watched_company_id=entry.watched_company_id,
        company_name=entry.company_name,
        careers_page_url=entry.careers_page_url,
        ats_type=entry.ats_type.value,
        keywords=entry.keywords,
        is_active=entry.is_active,
        created_at=entry.created_at,
    )


@router.get("/limits", response_model=LimitsResponse)
async def career_watch_limits(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> LimitsResponse:
    max_companies, interval = await get_career_watch_limits(db, user=user)
    from app.services.career_watch.limits import count_active_watches

    active = await count_active_watches(db, user_id=user.id)
    return LimitsResponse(
        max_companies=max_companies,
        poll_interval_minutes=interval,
        active_watches=active,
    )


@router.post("/detect", response_model=DetectResponse)
async def career_watch_detect(
    body: DetectRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> DetectResponse:
    del user
    result = await detect_careers_page(body.careers_page_url)
    return DetectResponse(**result)


@router.get("/watches", response_model=list[WatchResponse])
async def career_watch_list(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[WatchResponse]:
    entries = await list_watchlist(db, user_id=user.id)
    return [_watch_response(entry) for entry in entries]


@router.post("/watches", response_model=WatchResponse, status_code=status.HTTP_201_CREATED)
async def career_watch_create(
    body: WatchCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> WatchResponse:
    try:
        entry = await add_watch(
            db,
            user_id=user.id,
            user=user,
            careers_page_url=body.careers_page_url,
            company_name=body.company_name,
            keywords=body.keywords,
        )
    except CareerWatchLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "career_watch_limit",
                "limit": exc.limit,
                "current": exc.current,
            },
        ) from exc
    await db.commit()
    return _watch_response(entry)


@router.patch("/watches/{watch_id}", response_model=WatchResponse)
async def career_watch_update(
    watch_id: uuid.UUID,
    body: WatchUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> WatchResponse:
    try:
        entry = await update_watch_keywords(
            db,
            user_id=user.id,
            watch_id=watch_id,
            keywords=body.keywords,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="watch not found") from exc
    await db.commit()
    return _watch_response(entry)


@router.delete("/watches/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def career_watch_delete(
    watch_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    try:
        await remove_watch(db, user_id=user.id, watch_id=watch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="watch not found") from exc
    await db.commit()


@router.get("/alerts", response_model=list[AlertResponse])
async def career_watch_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[AlertResponse]:
    rows = (
        await db.execute(
            select(CareerAlert, CareerJobCache)
            .join(CareerJobCache, CareerAlert.career_job_cache_id == CareerJobCache.id)
            .where(CareerAlert.user_id == user.id)
            .where(
                CareerAlert.status.in_(
                    [
                        CareerAlertStatus.pending,
                        CareerAlertStatus.sent,
                    ]
                )
            )
            .order_by(CareerAlert.created_at.desc())
            .limit(100)
        )
    ).all()
    return [
        AlertResponse(
            id=alert.id,
            status=alert.status.value,
            match_score=alert.match_score,
            match_reason=alert.match_reason,
            created_at=alert.created_at,
            notified_at=alert.notified_at,
            job_title=job.title,
            job_location=job.location,
            apply_url=job.apply_url,
        )
        for alert, job in rows
    ]


@router.post("/alerts/{alert_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def career_watch_dismiss_alert(
    alert_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    try:
        await dismiss_alert(db, user_id=user.id, alert_id=alert_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="alert not found") from exc
    await db.commit()


__all__ = ["router"]
