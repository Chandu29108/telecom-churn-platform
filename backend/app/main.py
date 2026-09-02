import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from slowapi import Limiter

from .database import engine, Base, SessionLocal
from .config import (
    CORS_ORIGINS, SECRET_KEY, ENVIRONMENT, RATE_LIMIT_DEFAULT, SENTRY_DSN,
    LLM_PROVIDER, R2_BUCKET_NAME, R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
)
from .routers import analysis, prediction, auth, copilot, audit
from .logging_config import configure_logging

# noqa: F401 — imported so Base.metadata sees every model when
# create_all() runs below (dev-only path, see comment there).
from . import models_db  # noqa: F401

configure_logging()
logger = logging.getLogger("churn_platform")

# Sentry — optional, config-driven (same pattern as R2/LLM-provider): only
# initialized if SENTRY_DSN is set, so local dev/CI never need an account.
# Explicitly excluded for ENVIRONMENT=test regardless of SENTRY_DSN, since
# .env is loaded the same way whether you run `uvicorn` or `pytest` — a
# real DSN sitting in .env for local manual testing would otherwise mean
# every pytest run reports its own deliberately-thrown test exceptions
# (test_error_handling.py, test_upload_hardening.py, etc.) to Sentry as
# if they were real production incidents.
if SENTRY_DSN and ENVIRONMENT != "test":
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=SENTRY_DSN, environment=ENVIRONMENT, traces_sample_rate=0.1)
        logger.info("sentry.initialized environment=%s", ENVIRONMENT)
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk isn't installed — add it to requirements.txt.")

# Refuse to boot in production with the placeholder secret — a JWT signed
# with a known default key is not a security boundary at all. Local/dev
# runs are unaffected so `docker compose up` still works with zero config.
if ENVIRONMENT == "production" and SECRET_KEY == "dev-secret-change-me-before-deploying":
    raise RuntimeError(
        "Refusing to start: SECRET_KEY is still the default dev value. "
        "Set a real, random SECRET_KEY environment variable before deploying to production "
        "(e.g. `python -c \"import secrets; print(secrets.token_hex(32))\"`)."
    )

# These two are warnings, not hard failures like SECRET_KEY above — the
# app still functions without them (the copilot feature just returns a
# 503 per-request; model storage falls back to local disk). But both are
# easy to forget and fail silently otherwise, so make them loud and
# specific at boot rather than a bad surprise after the first redeploy.
if ENVIRONMENT == "production" and LLM_PROVIDER == "ollama":
    logger.warning(
        "startup.config_warning LLM_PROVIDER=ollama in production — Ollama has no "
        "managed equivalent on Render and the copilot feature will fail on every "
        "request. Set LLM_PROVIDER=openai with OPENAI_API_KEY (and optionally "
        "OPENAI_BASE_URL/OPENAI_MODEL) to use an OpenAI-compatible provider such as "
        "Groq instead."
    )

if ENVIRONMENT == "production" and not (
    R2_BUCKET_NAME and R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY
):
    logger.warning(
        "startup.config_warning Cloudflare R2 is not configured in production — trained "
        "models are being written to local disk, which is EPHEMERAL on Render's web "
        "service and will be lost on the next redeploy/restart. Set R2_BUCKET_NAME, "
        "R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, and R2_SECRET_ACCESS_KEY to persist models "
        "to object storage instead."
    )

# Dev-only convenience: creates tables on startup if they don't exist yet,
# so a fresh `docker compose up` / local run works with zero migration
# steps. In production this must NOT run alongside Alembic — the Docker
# CMD already runs `alembic upgrade head` before the app starts, and having
# BOTH mechanisms active means a model change without a matching migration
# would get silently applied by create_all() (bypassing Alembic's version
# tracking entirely), so `alembic upgrade head` on a fresh environment and
# the live schema could quietly diverge. Alembic is the only source of
# truth for schema changes once ENVIRONMENT=production.
if ENVIRONMENT != "production":
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Telecom Churn Prediction API",
    description="Upload usage data, get a trained churn model, dashboard "
                "metrics, SHAP-explained risk scores, business insights, "
                "recommendations, and a copilot to ask questions about the "
                "results — all scoped to your organization.",
    version="2.0.0",
    # Swagger/ReDoc expose the full API schema, including internal field
    # names, to anyone who finds the URL (audit report, Part 6, finding
    # #8). Not a vulnerability by itself, but no reason to leave it
    # public once this is a real deployment rather than a dev/demo box.
    docs_url="/docs" if ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if ENVIRONMENT != "production" else None,
    openapi_url="/openapi.json" if ENVIRONMENT != "production" else None,
)

limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT_DEFAULT])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(analysis.router)
app.include_router(prediction.router)
app.include_router(copilot.router)
app.include_router(audit.router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Tags every request/response with an ID so a client-visible error and
    a server-side log line (and, if a global handler fires, the exception
    traceback) can be correlated without exposing the traceback itself."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Baseline hardening headers (production-readiness audit, Phase 5).
    This is a pure JSON API consumed by a separate frontend origin, so
    these can be strict — there's no first-party HTML page here that
    needs relaxed rules, except /docs and /redoc, which are only ever
    enabled outside production (see the FastAPI() constructor above) and
    are therefore excluded from the strict CSP below."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Only meaningful over HTTPS, which is how Render terminates TLS in
    # front of the app — harmless but pointless to send over local HTTP.
    if ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        # default-src 'none': correct for a pure JSON API with no HTML
        # views to render. Swagger/ReDoc are disabled in production (see
        # docs_url=None above), so there's no in-app page that needs a
        # more permissive policy to load its own JS/CSS.
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catches anything routers/dependencies didn't already turn into an
    HTTPException (FastAPI/Starlette handle those separately and this
    handler never sees them). Without this, an uncaught error — a bad SQL
    constraint, a pandas edge case on a weird CSV, anything — would return
    Starlette's default response, which in debug contexts (and some
    deployment configs) includes the stack trace, file paths, and
    sometimes query parameters straight to the client. Always log the full
    exception server-side; always return a generic, safe message to the
    client along with the request ID so it can be looked up in logs."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(
        "unhandled_exception request_id=%s method=%s path=%s",
        request_id, request.method, request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred. Please try again, and "
                       "contact support with this request ID if it persists.",
            "request_id": request_id,
        },
    )


logger.info("Telecom Churn Prediction API starting up (environment=%s)", ENVIRONMENT)


@app.on_event("startup")
def recover_stale_jobs() -> None:
    """Restart-recovery sweep for FastAPI BackgroundTasks' biggest
    limitation: a job that was QUEUED or PROCESSING when the process died
    (crash, deploy, OOM-kill) has no worker left to finish it and would
    otherwise stay "in progress" forever from the frontend's point of
    view. On every boot, mark any job stuck in that state as FAILED with
    a clear, retryable error — the temp upload file is intentionally left
    on disk so /jobs/{id}/retry still works after this.

    This is exactly the gap a real queue (Celery + Redis) closes
    natively via task acknowledgement/re-delivery — see the migration-
    trigger note in routers/analysis.py.
    """
    from datetime import datetime, timedelta
    from .models_db import Job

    db = SessionLocal()
    try:
        stale_cutoff = datetime.utcnow() - timedelta(minutes=30)
        stale_jobs = (
            db.query(Job)
            .filter(Job.status.in_(["QUEUED", "PROCESSING"]), Job.created_at < stale_cutoff)
            .all()
        )
        for job in stale_jobs:
            job.status = "FAILED"
            job.error_message = "Interrupted by a server restart before completion. Please retry."
            job.completed_at = datetime.utcnow()
        if stale_jobs:
            db.commit()
            logger.warning("startup.recovered_stale_jobs count=%s", len(stale_jobs))
    except Exception:
        # Never block startup on this — worst case, a stale job just sits
        # there until the next boot or a manual check.
        logger.exception("startup.stale_job_recovery_failed")
    finally:
        db.close()


@app.get("/api/health")
def health():
    """Liveness: is the process up and serving requests at all."""
    return {"status": "ok"}


@app.get("/api/ready")
def ready():
    """Readiness: is the process able to actually do its job right now —
    i.e. can it reach the database. A load balancer/orchestrator should
    stop routing traffic here (but not restart the process) if this
    fails, which /api/health alone can't express."""
    from sqlalchemy import text
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return {"status": "ready"}
    except Exception:
        logger.exception("readiness_check_failed")
        return JSONResponse(status_code=503, content={"status": "not_ready"})


if ENVIRONMENT != "production":
    @app.get("/api/debug/sentry-test")
    def sentry_test():
        """Deliberately throws, so you can confirm Sentry is actually
        receiving events end-to-end (not just that sentry_sdk.init() ran
        without error) — see the production-readiness audit, Phase 7.
        Only registered outside production; doesn't exist at all on a
        production deploy, so there's no route to probe/abuse there."""
        raise RuntimeError("This is a deliberate test error for Sentry verification.")
