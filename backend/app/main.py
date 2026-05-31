from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.db.engine import async_session_factory
from app.limiter import limiter
from app.llm.factory import get_all_providers
from app.routers import auth, billing, export, llm, phases, resume, sessions
from app.services.billing.bootstrap import (
    assert_canonical_codes_resolve,
    seed_plan_configs_if_empty,
)
from app.services.session_store import close_redis, health_check, init_redis

# ---------------------------------------------------------------------------
# Logging & observability
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger()

if settings.SENTRY_DSN:
    sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1)


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    # Seed PlanConfig + assert all 10 canonical billing codes resolve
    # (IMPLEMENTATION_PLAN §7.2).  Failures here are logged at WARN and
    # tolerated in local/development; CI's staging gate fails on any gap.
    if settings.DATABASE_URL:
        try:
            async with async_session_factory() as db_session:
                await seed_plan_configs_if_empty(db_session)
                unresolved = await assert_canonical_codes_resolve(db_session)
                if unresolved and settings.APP_ENV in {"ci", "staging", "production"}:
                    raise RuntimeError(
                        "startup_price_gap: unresolved Stripe pricing codes: "
                        + ", ".join(unresolved)
                    )
                await db_session.commit()
        except Exception as exc:  # noqa: BLE001 - boot-time best effort
            log.warning("billing.bootstrap.skipped", error=str(exc))
    log.info("startup", provider=settings.LLM_PROVIDER, model=settings.LLM_MODEL)
    yield
    await close_redis()
    log.info("shutdown")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Smart Resume Agent API", version="1.0.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _cors_headers(request: Request) -> dict[str, str]:
    """Return CORS headers based on the incoming Origin."""
    origin = request.headers.get("origin", "")
    allowed = origin if origin in settings.ALLOWED_ORIGINS else (
        settings.ALLOWED_ORIGINS[0] if settings.ALLOWED_ORIGINS else "*"
    )
    return {
        "Access-Control-Allow-Origin": allowed,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Ensure HTTPException responses (404, 422, etc.) always carry CORS headers.

    Also forwards any ``exc.headers`` (e.g. ``WWW-Authenticate``) so auth
    routes can advertise the expected scheme on 401.
    """
    headers = _cors_headers(request)
    if exc.headers:
        headers.update(exc.headers)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return JSON errors with CORS headers so the browser shows the real failure."""
    log.error("unhandled_exception", path=str(request.url.path), error=str(exc))
    msg = str(exc)
    if "invalid_api_key" in msg or "AuthenticationError" in type(exc).__name__:
        return JSONResponse(
            status_code=502,
            content={
                "detail": (
                    "LLM authentication failed. "
                    "Check your API key in the browser UI or in backend/.env."
                )
            },
            headers=_cors_headers(request),
        )
    return JSONResponse(
        status_code=500,
        content={"detail": f"Server error: {msg}"},
        headers=_cors_headers(request),
    )


# Include routers
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(sessions.router)
app.include_router(resume.router)
app.include_router(phases.router)
app.include_router(export.router)
app.include_router(llm.router)


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    store_status = await health_check()
    return {
        "status": "ok",
        "provider": settings.LLM_PROVIDER,
        "model": settings.LLM_MODEL,
        **store_status,
    }


@app.get("/api/llm/providers")
async def list_providers():
    """
    Returns ALL supported providers + their model lists.
    Each entry includes `has_env_key` so the UI knows whether
    a .env key is already configured (green badge) or the user
    must supply their own (BYOK input field).
    """
    return {"providers": get_all_providers()}
