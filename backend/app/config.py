"""
Central configuration, read from environment variables (.env in local dev,
platform env vars on Render). Keeping this in one place means Docker,
docker-compose, and Render can all inject the same variable names without
code changes.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env", override=False)

# Postgres — Render/Docker inject DATABASE_URL directly. Local dev falls
# back to a docker-compose service name so `docker compose up` works with
# zero manual config.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://churn_user:churn_pass@db:5432/churn_db",
)

# Where trained models / uploaded artifacts are persisted between requests.
MODEL_DIR = Path(os.getenv("MODEL_DIR", BASE_DIR / "storage" / "models"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "storage" / "uploads"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Comma-separated list, e.g. "https://your-app.vercel.app,http://localhost:5173"
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

# Decision threshold used when converting probability -> CHURN_FLAG,
# matches the 0.45 operating point chosen in the source notebook's
# threshold analysis (Section 5).
CHURN_THRESHOLD = float(os.getenv("CHURN_THRESHOLD", "0.45"))

RISK_TIER_BOUNDS = {
    "Critical": 0.80,
    "High": 0.60,
    "Medium": 0.45,
    "Low": 0.0,
}

# --------------------------------------------------------------------------- #
# Auth / multi-tenancy
# --------------------------------------------------------------------------- #
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# NEVER ship the default secret to production — main.py refuses to start in
# production if this hasn't been overridden by a real secret env var.
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me-before-deploying")
JWT_ALGORITHM = "HS256"
# NOTE: ACCESS_TOKEN_EXPIRE_MINUTES itself now lives further down, next to
# the refresh-token settings it was split from — kept as one clearly-owned
# block instead of two definitions of the same setting in different places.

# --------------------------------------------------------------------------- #
# LLM copilot — pluggable provider, defaults to a local/free Ollama model so
# the platform never requires a paid API key to run the copilot feature.
# Swap LLM_PROVIDER to "openai" / "gemini" / "anthropic" later without
# touching any router code, same pattern as the AI Financial Research
# Assistant project's provider abstraction.
# --------------------------------------------------------------------------- #
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

# OpenAI-compatible provider (see app/llm/openai_compatible_provider.py) —
# works with OpenAI itself or any provider implementing the same API shape
# (Groq, Together, Fireworks, OpenRouter). Set LLM_PROVIDER=openai and
# these three to use it; OPENAI_BASE_URL defaults to Groq (free tier, no
# credit card to start) since Ollama has no equivalent on Render — see
# the production-readiness audit, Phase 3. gpt-oss-20b is Groq's current
# recommended fast/free-tier model as of their June 2026 deprecation of
# the old llama-3.1-8b-instant / llama-3.3-70b-versatile names.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "openai/gpt-oss-20b")

# --------------------------------------------------------------------------- #
# Rate limiting (slowapi / limits syntax, e.g. "60/minute")
# --------------------------------------------------------------------------- #
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")
RATE_LIMIT_UPLOAD = os.getenv("RATE_LIMIT_UPLOAD", "10/minute")
RATE_LIMIT_AUTH = os.getenv("RATE_LIMIT_AUTH", "10/minute")

# --- Auth -------------------------------------------------------------- #
# HS256 JWT signing key. The fallback value is intentionally obviously
# insecure so it's impossible to miss in logs/code review — main.py logs
# a loud warning on startup if this hasn't been overridden. Generate a
# real one with: python -c "import secrets; print(secrets.token_urlsafe(48))"
    # Nothing else in this codebase references JWT_SECRET_KEY (security.py
    # uses SECRET_KEY above) — this was a dead, unused duplicate definition
    # that risked someone editing the wrong variable during a real
    # incident. Removed rather than kept "just in case".

# --- Upload hardening ---------------------------------------------------- #
# Prevents a single request from exhausting memory/disk or tying up a
# worker for minutes retraining on an unreasonably large file.
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
MAX_UPLOAD_ROWS = int(os.getenv("MAX_UPLOAD_ROWS", "300000"))

# --------------------------------------------------------------------------- #
# Model storage — Cloudflare R2 in production, local disk fallback for dev.
# See app/model_store.py for the abstraction. All four must be set for R2
# to be used; if any are missing, model_store.get_model_store() falls back
# to local disk under MODEL_DIR (fine for local dev, NOT safe on platforms
# with an ephemeral filesystem like Render's web service disk).
# --------------------------------------------------------------------------- #
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "")
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_ENDPOINT_URL = os.getenv(
    "R2_ENDPOINT_URL",
    f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else "",
)
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")

# --------------------------------------------------------------------------- #
# Refresh tokens (httpOnly cookie) — see app/security.py + routers/auth.py.
# Access tokens stay short-lived and travel as a normal Bearer token (JSON
# body), unchanged from before; the refresh token is the new piece, and it
# never touches JS-reachable storage. ACCESS_TOKEN_EXPIRE_MINUTES' default
# is intentionally much shorter than the old 60/120-minute default — the
# refresh flow means a short access token no longer costs UX, only caps
# how long a stolen access token (e.g. via a future XSS bug) stays useful.
# --------------------------------------------------------------------------- #
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
REFRESH_COOKIE_NAME = "churn_refresh_token"
# CSRF double-submit pair for the refresh/logout endpoints (see
# routers/auth.py::_verify_csrf). The cookie proves the request carries
# our session; the header proves the request was built by JS that
# actually received our JSON response (delivered once at
# login/register/refresh) — a cross-site attacker's page can trigger the
# cookie being sent automatically but can't read our response body to
# get this value, since CORS only allows the real frontend origin.
CSRF_COOKIE_NAME = "churn_csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
# Cross-site (Vercel <-> Render) cookies need SameSite=None + Secure. Local
# dev (localhost:5173 -> localhost:8000) is same-site despite the different
# port, so Lax + non-Secure works there without any browser flags.
COOKIE_SAMESITE = "none" if ENVIRONMENT == "production" else "lax"
COOKIE_SECURE = ENVIRONMENT == "production"

# --------------------------------------------------------------------------- #
# Email (verification + password reset) — see app/email/.
# EMAIL_PROVIDER=console (default) logs the email instead of sending it, so
# local dev and CI never need real credentials. Set EMAIL_PROVIDER=resend
# and RESEND_API_KEY to send for real. See app/email/README or the audit
# report for why Resend was picked over SES/SendGrid for this stack.
# --------------------------------------------------------------------------- #
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "console")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM_ADDRESS = os.getenv("EMAIL_FROM_ADDRESS", "no-reply@yourdomain.example")
# Used to build links inside emails (e.g. https://app.yourdomain.com/verify-email?token=...).
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Billing (Lemon Squeezy — chosen over Stripe because Stripe is invite-only
# for India-based accounts; Lemon Squeezy is a Merchant of Record, so it
# also handles global sales-tax/VAT/GST compliance rather than leaving
# that to us). All four are required for the billing endpoints to work;
# unset in local dev is fine — checkout/webhook just aren't exercised.
LEMON_SQUEEZY_API_KEY = os.getenv("LEMON_SQUEEZY_API_KEY", "")
LEMON_SQUEEZY_STORE_ID = os.getenv("LEMON_SQUEEZY_STORE_ID", "")
LEMON_SQUEEZY_PRO_VARIANT_ID = os.getenv("LEMON_SQUEEZY_PRO_VARIANT_ID", "")
# Set when creating the webhook in the Lemon Squeezy dashboard (Settings >
# Webhooks) — used to verify incoming webhook payloads are genuinely from
# Lemon Squeezy (HMAC-SHA256 over the raw body) rather than forged.
LEMON_SQUEEZY_WEBHOOK_SECRET = os.getenv("LEMON_SQUEEZY_WEBHOOK_SECRET", "")
EMAIL_VERIFICATION_EXPIRE_HOURS = int(os.getenv("EMAIL_VERIFICATION_EXPIRE_HOURS", "24"))
PASSWORD_RESET_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", "30"))

# --------------------------------------------------------------------------- #
# Upload hardening, part 2 (see Part 11 of the audit — wide-CSV memory risk)
# --------------------------------------------------------------------------- #
MAX_UPLOAD_COLUMNS = int(os.getenv("MAX_UPLOAD_COLUMNS", "500"))

# --------------------------------------------------------------------------- #
# Background job processing (see routers/analysis.py + app/models_db.py::Job)
# --------------------------------------------------------------------------- #
MAX_JOB_RETRIES = int(os.getenv("MAX_JOB_RETRIES", "3"))
# How long a QUEUED/PROCESSING job is allowed to run before a restart-
# recovery sweep (see main.py startup) treats it as abandoned. Generous on
# purpose — training + SHAP on a large file can legitimately take minutes.
JOB_STALE_AFTER_MINUTES = int(os.getenv("JOB_STALE_AFTER_MINUTES", "30"))

# --------------------------------------------------------------------------- #
# Observability — error tracking (see Part 13 of the audit report:
# lightweight observability first, no Prometheus/Grafana until scale
# actually justifies it). Empty by default; Sentry is only initialized if
# this is set, so local dev/CI never need an account for it.
# --------------------------------------------------------------------------- #
SENTRY_DSN = os.getenv("SENTRY_DSN", "")

# --------------------------------------------------------------------------- #
# Personal vs organization accounts (see routers/auth.py register()).
# A personal workspace is a normal Organization row with account_type=
# "personal" — capped at one seat and a smaller upload ceiling by default,
# both overridable per-org later (e.g. a paid personal tier) since they
# live on the Organization row, not a hardcoded constant.
# --------------------------------------------------------------------------- #
PERSONAL_MAX_SEATS = int(os.getenv("PERSONAL_MAX_SEATS", "1"))
PERSONAL_MAX_UPLOAD_ROWS = int(os.getenv("PERSONAL_MAX_UPLOAD_ROWS", "5000"))
