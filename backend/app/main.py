from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.llm.factory import get_all_providers
from app.routers import export, phases, resume, sessions
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
# Rate limiter
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return JSON errors so CORS headers are present and the browser shows the real failure."""
    log.error("unhandled_exception", path=str(request.url.path), error=str(exc))
    # Surface LLM auth failures clearly — most common local-dev issue
    msg = str(exc)
    if "invalid_api_key" in msg or "AuthenticationError" in type(exc).__name__:
        return JSONResponse(
            status_code=502,
            content={
                "detail": (
                    "LLM authentication failed. Check OPENAI_API_KEY (or your provider key) "
                    "in backend/.env, then restart the backend. "
                    "For free local inference, set LLM_PROVIDER=ollama and run Ollama."
                )
            },
        )
    return JSONResponse(status_code=500, content={"detail": "Internal server error. Check backend logs."})


# Include routers
app.include_router(sessions.router)
app.include_router(resume.router)
app.include_router(phases.router)
app.include_router(export.router)


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
