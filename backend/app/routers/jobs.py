"""Job search routes (RP3 — IMPLEMENTATION_PLAN §6 Jobs)."""

from __future__ import annotations

import json
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import job_fit as job_fit_agent
from app.agent import job_title_suggestions
from app.agent.title_fit_insights import enrich_title_suggestions
from app.db.engine import get_db
from app.llm.factory import get_llm_client_for_step
from app.llm.token_accounting import llm_accounting_context
from app.limiter import limiter, rate_limit_key
from app.models.fit import FitAnalysisOutput
from app.models.fit_analysis import FitAnalysis
from app.models.billing import Subscription, SubscriptionStatus
from app.models.jobs import AlertFrequency, SavedJob, SavedSearch
from app.models.user import User
from app.services.auth.dependencies import get_current_user
from app.services.auth.tokens import decode_access_token
from app.services.billing.exceptions import (
    AccountSuspendedError,
    PlanLimitReachedError,
    SubscriptionRequiredError,
)
from app.services.billing.quota import QuotaAction, check_and_increment_quota
from app.services.jobs.job_service import (
    get_job_by_id,
    list_saved_jobs,
    normalize_query,
    run_keyword_search,
    run_resume_match,
)
from app.services.jobs.schemas import (
    JobMatchRequest,
    JobPreferencesOut,
    JobPreferencesUpdate,
    JobResult,
    JobSearchRequest,
    JobSearchResponse,
    JobTitleSuggestionsOut,
    PreferredTitlesOut,
    PreferredTitlesUpdate,
    SavedSearchCreate,
    SavedSearchOut,
    SavedSearchUpdate,
)
from app.services.jobs.preferred_titles import (
    MAX_PREFERRED_JOB_TITLES,
    MIN_PREFERRED_JOB_TITLES,
    PREFERRED_TITLES_CONFIRMED_AT_KEY,
    PREFERRED_TITLES_KEY,
    PREFERRED_TITLES_SOURCE_HASH_KEY,
    compute_master_resume_hash,
    get_preferred_titles,
    has_confirmed_preferred_titles,
    is_source_stale,
    search_filters_from_user,
    set_preferred_titles,
)
from app.services.master_resume import crud as master_crud
from app.services.retrieval.exceptions import MasterResumeRequiredError

logger = structlog.get_logger(__name__)


def _min_titles_unlock_message() -> str:
    if MIN_PREFERRED_JOB_TITLES == 1:
        return "Pick a job title to unlock free corpus search."
    return (
        f"Pick at least {MIN_PREFERRED_JOB_TITLES} job titles to "
        "unlock free corpus search."
    )

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
log = structlog.get_logger("jobs.router")

MAX_SAVED_SEARCHES = 10
MAX_ALERT_SEARCHES = 5


async def _has_active_subscription(db: AsyncSession, *, user_id: uuid.UUID) -> bool:
    from datetime import datetime, timezone

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
    return sub is not None


async def _require_active_subscription(
    db: AsyncSession, *, user_id: uuid.UUID
) -> None:
    if not await _has_active_subscription(db, user_id=user_id):
        raise HTTPException(status_code=402, detail={"code": "subscription_required"})


async def _require_job_search_access(
    db: AsyncSession,
    *,
    user: User,
    expand: bool,
) -> None:
    """Paid users get full search; free users with confirmed titles get corpus search.

    All 402 responses include ``resolution`` so legacy clients that only checked
    for ``code=="subscription_required"`` still get a routable hint
    (``upgrade`` vs ``choose_job_titles``) without needing to learn every new
    ``code`` value.
    """
    if await _has_active_subscription(db, user_id=user.id):
        return
    if expand:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "subscription_required",
                "resolution": "upgrade",
                "message": "Expanded job search requires a paid plan.",
            },
        )
    if has_confirmed_preferred_titles(user):
        return
    if get_preferred_titles(user):
        raise HTTPException(
            status_code=402,
            detail={
                "code": "preferred_titles_incomplete",
                "resolution": "choose_job_titles",
                "min_required": MIN_PREFERRED_JOB_TITLES,
                "message": _min_titles_unlock_message(),
            },
        )
    raise HTTPException(
        status_code=402,
        detail={
            "code": "job_titles_required",
            "resolution": "choose_job_titles",
            "min_required": MIN_PREFERRED_JOB_TITLES,
            "message": _min_titles_unlock_message(),
        },
    )


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
    return rate_limit_key(request)


def _merge_filters(
    user: User, request_filters: dict
) -> dict:
    defaults = search_filters_from_user(user)
    defaults.update(request_filters or {})
    return defaults


async def _preferences_response(
    db: AsyncSession, user: User
) -> JobPreferencesOut:
    titles = get_preferred_titles(user)
    stale = False
    if len(titles) >= MIN_PREFERRED_JOB_TITLES:
        resume = await master_crud.get_raw_resume(db, user_id=user.id)
        if resume is not None and (resume.raw_text or "").strip():
            current_hash = compute_master_resume_hash(resume.raw_text)
            stale = is_source_stale(user, current_hash=current_hash)
    return JobPreferencesOut(
        blocked_companies=list(user.blocked_companies or []),
        default_filters=search_filters_from_user(user),
        preferred_titles=titles,
        preferred_titles_confirmed=len(titles) >= MIN_PREFERRED_JOB_TITLES,
        preferred_titles_stale=stale,
        min_preferred_titles=MIN_PREFERRED_JOB_TITLES,
        max_preferred_titles=MAX_PREFERRED_JOB_TITLES,
    )


def _blocked(user: User) -> list[str]:
    return list(user.blocked_companies or [])


async def _require_subscription_quota(
    db: AsyncSession,
    *,
    user: User,
    action: QuotaAction,
    charge: bool,
) -> None:
    if not charge:
        return
    try:
        await check_and_increment_quota(db, user=user, action=action)
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


class FitJobResponse(BaseModel):
    analysis_id: str
    result: FitAnalysisOutput


@router.post("/search", response_model=JobSearchResponse)
@limiter.limit("60/hour", key_func=_rate_limit_user_key)
async def search_jobs(
    request: Request,
    body: JobSearchRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _require_job_search_access(db, user=user, expand=body.expand)
    filters = _merge_filters(user, body.filters)
    jobs, total, stale, message, charge, source = await run_keyword_search(
        db,
        user_id=user.id,
        query=body.query,
        location=body.location,
        filters=filters,
        page=body.page,
        page_size=body.page_size,
        blocked_companies=_blocked(user),
        expand=body.expand,
    )
    await _require_subscription_quota(
        db, user=user, action=QuotaAction.job_search, charge=charge
    )
    await db.commit()
    return JobSearchResponse(
        jobs=jobs,
        total=total,
        page=body.page,
        page_size=body.page_size,
        results_may_be_stale=stale,
        message=message,
        source=source,
    )


@router.get("/title-suggestions", response_model=JobTitleSuggestionsOut)
@limiter.limit("30/hour", key_func=_rate_limit_user_key)
async def get_title_suggestions(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    resume = await master_crud.get_raw_resume(db, user_id=user.id)
    if resume is None or not (resume.raw_text or "").strip():
        raise HTTPException(
            status_code=422,
            detail="Build your master resume on /profile before choosing job titles.",
        )

    llm_client = None
    try:
        with llm_accounting_context(step="job_title_suggestions", user_id=str(user.id)):
            llm_client = get_llm_client_for_step("job_title_suggestions")
            suggestions, held, source = await job_title_suggestions.suggest_job_titles(
                resume_text=resume.raw_text,
                parsed_sections=resume.parsed_sections,
                llm_client=llm_client,
            )
    except Exception:  # noqa: BLE001
        suggestions, held, source = await job_title_suggestions.suggest_job_titles(
            resume_text=resume.raw_text,
            parsed_sections=resume.parsed_sections,
            llm_client=None,
        )
    enriched = enrich_title_suggestions(
        suggestions,
        resume_text=resume.raw_text or "",
        held_titles=held,
        parsed_sections=resume.parsed_sections,
    )
    return JobTitleSuggestionsOut(
        suggestions=[
            {
                "title": row.title,
                "fit_score": row.fit_score,
                "strengths": row.strengths,
                "weaknesses": row.weaknesses,
            }
            for row in enriched
        ],
        held_titles=held,
        source=source,
        source_hash=compute_master_resume_hash(resume.raw_text),
    )


@router.put("/preferred-titles", response_model=PreferredTitlesOut)
@limiter.limit("30/hour", key_func=_rate_limit_user_key)
async def update_preferred_titles(
    request: Request,
    body: PreferredTitlesUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if len(body.titles) < MIN_PREFERRED_JOB_TITLES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "preferred_titles_incomplete",
                "min_required": MIN_PREFERRED_JOB_TITLES,
                "message": (
                    "Select a job title."
                    if MIN_PREFERRED_JOB_TITLES == 1
                    else f"Select at least {MIN_PREFERRED_JOB_TITLES} job titles."
                ),
            },
        )
    resume = await master_crud.get_raw_resume(db, user_id=user.id)
    source_hash = (
        compute_master_resume_hash(resume.raw_text)
        if resume is not None and (resume.raw_text or "").strip()
        else None
    )
    saved = set_preferred_titles(user, body.titles, source_hash=source_hash)
    await db.commit()
    return PreferredTitlesOut(
        titles=saved,
        confirmed=len(saved) >= MIN_PREFERRED_JOB_TITLES,
        stale=False,
        min_required=MIN_PREFERRED_JOB_TITLES,
        max_allowed=MAX_PREFERRED_JOB_TITLES,
    )


@router.post("/match", response_model=JobSearchResponse)
@limiter.limit("20/hour", key_func=_rate_limit_user_key)
async def match_jobs(
    request: Request,
    body: JobMatchRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _require_active_subscription(db, user_id=user.id)
    jobs, total, stale, message, charge = await run_resume_match(
        db,
        user_id=user.id,
        page=body.page,
        page_size=body.page_size,
        blocked_companies=_blocked(user),
    )
    if message and not jobs and not charge:
        raise HTTPException(status_code=422, detail=message)
    await _require_subscription_quota(
        db, user=user, action=QuotaAction.job_search, charge=charge
    )
    await db.commit()
    return JobSearchResponse(
        jobs=jobs,
        total=total,
        page=body.page,
        page_size=body.page_size,
        results_may_be_stale=stale,
        message=message,
    )


@router.get("/saved", response_model=list[JobResult])
@limiter.limit("120/minute")
async def list_saved(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await list_saved_jobs(
        db, user_id=user.id, blocked_companies=_blocked(user)
    )


@router.get("/saved-searches", response_model=list[SavedSearchOut])
@limiter.limit("120/minute")
async def list_saved_searches(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    rows = (
        await db.execute(
            select(SavedSearch)
            .where(SavedSearch.user_id == user.id)
            .order_by(SavedSearch.created_at.desc())
        )
    ).scalars().all()
    return [
        SavedSearchOut(
            id=str(r.id),
            name=r.name,
            query=r.query,
            location=r.location,
            filters=dict(r.filters or {}),
            alert_frequency=r.alert_frequency.value,
            last_alerted_at=r.last_alerted_at.isoformat() if r.last_alerted_at else None,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.post("/saved-searches", response_model=SavedSearchOut, status_code=201)
@limiter.limit("30/minute")
async def create_saved_search(
    request: Request,
    body: SavedSearchCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Serialize per-user limit accounting to avoid race over-inserts.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    count = (
        await db.execute(
            select(func.count())
            .select_from(SavedSearch)
            .where(SavedSearch.user_id == user.id)
        )
    ).scalar_one()
    if count >= MAX_SAVED_SEARCHES:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum {MAX_SAVED_SEARCHES} saved searches per user.",
        )

    try:
        alert = AlertFrequency(body.alert_frequency)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid alert_frequency.") from None

    if alert != AlertFrequency.off:
        alert_count = (
            await db.execute(
                select(func.count())
                .select_from(SavedSearch)
                .where(SavedSearch.user_id == user.id)
                .where(SavedSearch.alert_frequency != AlertFrequency.off)
            )
        ).scalar_one()
        if alert_count >= MAX_ALERT_SEARCHES:
            raise HTTPException(
                status_code=422,
                detail=f"Maximum {MAX_ALERT_SEARCHES} saved searches with alerts enabled.",
            )

    row = SavedSearch(
        id=uuid.uuid4(),
        user_id=user.id,
        name=body.name,
        query=normalize_query(body.query),
        location=body.location,
        filters=body.filters,
        alert_frequency=alert,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return SavedSearchOut(
        id=str(row.id),
        name=row.name,
        query=row.query,
        location=row.location,
        filters=dict(row.filters or {}),
        alert_frequency=row.alert_frequency.value,
        last_alerted_at=None,
        created_at=row.created_at.isoformat(),
    )


@router.patch("/saved-searches/{search_id}", response_model=SavedSearchOut)
@limiter.limit("30/minute")
async def update_saved_search(
    request: Request,
    search_id: str,
    body: SavedSearchUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    try:
        sid = uuid.UUID(search_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid saved search id.") from None

    row = (
        await db.execute(
            select(SavedSearch).where(
                SavedSearch.id == sid,
                SavedSearch.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Saved search not found.")

    new_alert = row.alert_frequency
    if body.alert_frequency is not None:
        try:
            new_alert = AlertFrequency(body.alert_frequency)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid alert_frequency.") from None

    if new_alert != AlertFrequency.off and row.alert_frequency == AlertFrequency.off:
        alert_count = (
            await db.execute(
                select(func.count())
                .select_from(SavedSearch)
                .where(SavedSearch.user_id == user.id)
                .where(SavedSearch.alert_frequency != AlertFrequency.off)
            )
        ).scalar_one()
        if alert_count >= MAX_ALERT_SEARCHES:
            raise HTTPException(
                status_code=422,
                detail=f"Maximum {MAX_ALERT_SEARCHES} saved searches with alerts enabled.",
            )

    if body.name is not None:
        row.name = body.name
    if body.query is not None:
        row.query = normalize_query(body.query)
    if body.location is not None:
        row.location = body.location
    if body.filters is not None:
        row.filters = body.filters
    row.alert_frequency = new_alert
    await db.commit()
    await db.refresh(row)
    return SavedSearchOut(
        id=str(row.id),
        name=row.name,
        query=row.query,
        location=row.location,
        filters=dict(row.filters or {}),
        alert_frequency=row.alert_frequency.value,
        last_alerted_at=row.last_alerted_at.isoformat() if row.last_alerted_at else None,
        created_at=row.created_at.isoformat(),
    )


@router.delete("/saved-searches/{search_id}", status_code=204)
@limiter.limit("30/minute")
async def delete_saved_search(
    request: Request,
    search_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        sid = uuid.UUID(search_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid saved search id.") from None

    row = (
        await db.execute(
            select(SavedSearch).where(
                SavedSearch.id == sid,
                SavedSearch.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Saved search not found.")
    await db.delete(row)
    await db.commit()


@router.get("/preferences", response_model=JobPreferencesOut)
@limiter.limit("120/minute")
async def get_preferences(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _preferences_response(db, user)


@router.put("/preferences", response_model=JobPreferencesOut)
@limiter.limit("30/minute")
async def update_preferences(
    request: Request,
    body: JobPreferencesUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if body.blocked_companies is not None:
        user.blocked_companies = [c.strip() for c in body.blocked_companies if c.strip()]
    if body.default_filters is not None:
        reserved = {
            PREFERRED_TITLES_KEY,
            PREFERRED_TITLES_CONFIRMED_AT_KEY,
            PREFERRED_TITLES_SOURCE_HASH_KEY,
        }
        filters = {
            k: v for k, v in (user.job_default_filters or {}).items() if k in reserved
        }
        for k, v in body.default_filters.items():
            if k in reserved:
                continue
            filters[k] = v
        user.job_default_filters = filters
    if body.preferred_titles is not None:
        resume = await master_crud.get_raw_resume(db, user_id=user.id)
        source_hash = (
            compute_master_resume_hash(resume.raw_text)
            if resume is not None and (resume.raw_text or "").strip()
            else None
        )
        set_preferred_titles(user, body.preferred_titles, source_hash=source_hash)
    await db.commit()
    return await _preferences_response(db, user)


@router.get("/{job_id}", response_model=JobResult)
@limiter.limit("120/minute")
async def get_job(
    request: Request,
    job_id: str,
    user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job id.") from None

    row = await get_job_by_id(db, jid)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    from app.services.jobs.filtering import filter_blocked_companies
    from app.services.jobs.job_service import job_cache_to_result

    results = filter_blocked_companies(
        [job_cache_to_result(row)],
        _blocked(user),
    )
    if not results:
        raise HTTPException(status_code=404, detail="Job not found.")
    return results[0]


@router.post("/{job_id}/fit", response_model=FitJobResponse)
@limiter.limit("20/hour", key_func=_rate_limit_user_key)
async def fit_job(
    request: Request,
    job_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job id.") from None

    row = await get_job_by_id(db, jid)
    if row is None or not row.description.strip():
        raise HTTPException(status_code=404, detail="Job not found.")

    await _require_active_subscription(db, user_id=user.id)
    await _require_subscription_quota(
        db, user=user, action=QuotaAction.fit_analysis, charge=True
    )

    with llm_accounting_context(step="job_fit", user_id=str(user.id)):
        llm = get_llm_client_for_step("job_fit")
        import asyncio

        queue: asyncio.Queue = asyncio.Queue()
        try:
            output = await job_fit_agent.run(
                db,
                user_id=user.id,
                jd_text=row.description,
                llm=llm,
                event_queue=queue,
            )
        except MasterResumeRequiredError:
            await db.rollback()
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "master_resume_required",
                    "message": "Upload a master resume on /profile before running fit analysis.",
                },
            )
        except Exception as exc:
            await db.rollback()
            log.exception("jobs.fit_failed", error=str(exc))
            raise HTTPException(status_code=500, detail="Fit analysis failed.") from exc

    analysis_id = uuid.uuid4()
    fit_row = FitAnalysis(
        id=analysis_id,
        user_id=user.id,
        jd_hash=str(jid),
        jd_text=row.description[:50000],
        result_json=json.loads(output.model_dump_json()),
    )
    db.add(fit_row)
    await db.commit()
    return FitJobResponse(analysis_id=str(analysis_id), result=output)


@router.post("/{job_id}/save", status_code=201)
@limiter.limit("60/minute")
async def save_job(
    request: Request,
    job_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job id.") from None

    if await get_job_by_id(db, jid) is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    existing = (
        await db.execute(
            select(SavedJob).where(
                SavedJob.user_id == user.id,
                SavedJob.job_cache_id == jid,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return {"id": str(existing.id), "job_id": job_id}

    bookmark = SavedJob(
        id=uuid.uuid4(),
        user_id=user.id,
        job_cache_id=jid,
    )
    db.add(bookmark)
    try:
        await db.commit()
        return {"id": str(bookmark.id), "job_id": job_id}
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(SavedJob).where(
                    SavedJob.user_id == user.id,
                    SavedJob.job_cache_id == jid,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return {"id": str(existing.id), "job_id": job_id}
        raise


@router.delete("/{job_id}/save", status_code=204)
@limiter.limit("60/minute")
async def unsave_job(
    request: Request,
    job_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job id.") from None

    row = (
        await db.execute(
            select(SavedJob).where(
                SavedJob.user_id == user.id,
                SavedJob.job_cache_id == jid,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Bookmark not found.")
    await db.delete(row)
    await db.commit()
