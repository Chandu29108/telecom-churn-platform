# v2.0 Changelog — Why Each Change Was Made

This document explains every structural change made to take the platform from a working
single-user demo to a multi-tenant, explainable, production-hardened product, and the specific
reasoning behind each one. It follows directly from the market research report's findings:
the core ML loop (upload → train → dashboard) was already commoditized by funded competitors
(Pecan AI, DataRobot, H2O.ai, Kumo.ai); the gaps that actually mattered were **explainability**,
**auth/multi-tenancy**, and **production readiness**.

---

## 1. Multi-tenancy & authentication

**What changed:** Added `Organization` and `User` tables, JWT-based login/register
(`app/security.py`, `app/deps.py`, `app/routers/auth.py`), and scoped every query in
`analysis.py`/`prediction.py`/`copilot.py` by `current_user.org_id`. Trained models moved from
one global `storage/models/latest_model.joblib` to per-org paths
(`storage/models/org_<id>/latest_model.joblib`).

**Why:** The single biggest blocker to calling this a "product" rather than a demo was that
every user shared one model and one set of analysis runs — two people uploading different
datasets would silently overwrite each other's trained model. This is also the #1 item on the
enterprise-readiness gap list from the market research (Section 8): no Tier-1 or even
mid-market telecom buyer will evaluate a tool where their data isn't isolated from anyone
else's. The registration flow (first user for an org name becomes "owner", later ones join as
"member") is a deliberate single-step tradeoff — a real invite/billing system is future work,
but requiring one before shipping isolation at all would have blocked everything else.

**Verified:** `tests/test_auth.py` and `tests/test_analysis.py::test_runs_are_isolated_between_organizations`
/ `test_cannot_fetch_another_orgs_run_by_id` / `tests/test_prediction.py::test_predict_models_are_isolated_between_organizations`
— all confirm one org cannot see or use another org's runs or trained models.

## 2. SHAP explainability

**What changed:** New `app/ml/explainability.py` wraps `shap.TreeExplainer` (exact for tree
ensembles like `GradientBoostingClassifier`). The dashboard's high-risk customer table (top 50)
and the single-customer Prediction page both now return, per customer, the top contributing
features with a signed value and a direction (`increases_risk` / `decreases_risk`).

**Why:** This was the single highest-ranked item in the market research's competitive-advantage
analysis (Section 6) — DataRobot, H2O.ai, and Kumo.ai all have per-prediction explainability;
this platform had none. A churn probability alone tells a retention agent *who* to call but not
*what to say* — "63% risk, driven by a 40% drop in incoming call minutes and a lapsed recharge"
is something a retention team can act on; "63% risk" alone is not.

**Performance decision:** SHAP is only ever computed for customers actually shown in the UI —
the top 50 in the dashboard table, or the single row on the Prediction page — never the full
uploaded dataset. Running exact SHAP over 100K+ rows synchronously in a request would make
uploads unacceptably slow; this keeps explanation cost bounded regardless of dataset size.

**Failure handling:** If SHAP explanation fails for any reason, the upload endpoint logs the
exception and returns the analysis with empty `top_factors` rather than failing the whole
request — explainability is a value-add, not a hard dependency of the core prediction flow.

**Verified:** `tests/test_analysis.py::test_upload_trains_model_and_returns_shap_factors` and
`tests/test_prediction.py::test_predict_uses_trained_model_and_shap_after_upload` confirm real
SHAP output shape and content, not just that the field exists.

## 3. LLM copilot (local, free by default)

**What changed:** A pluggable provider abstraction (`app/llm/base.py`, `ollama_provider.py`,
`factory.py`) and a new `/api/copilot` endpoint that answers questions about the current
analysis run, grounded strictly in that run's stored JSON (system prompt explicitly instructs
the model not to invent numbers). Defaults to a local Ollama server — no API key required.

**Why:** Ranked #2 in the competitive-advantage analysis — Pecan AI shipped a very similar
"ask your data" conversational layer in 2026, and it's the newest wedge every serious
competitor in this space is racing toward. Making it free/local by default (rather than
requiring an OpenAI/Anthropic/Gemini key) means the feature works in a demo, an interview
walkthrough, or someone else cloning the repo without anyone paying for API calls — and the
provider abstraction means swapping to a paid model later (for better quality at scale) is a
one-line `LLM_PROVIDER` change, not a rewrite of the router.

**Scope decision:** The copilot is deliberately *not* a general chatbot — it only answers from
one analysis run's context and says so plainly when the context doesn't have what's needed.
This is narrower and more defensible than an open-ended assistant, and it's honest about what
it does and doesn't know, which matters for a tool retention teams will actually rely on.

**Failure handling:** If Ollama isn't running, the endpoint returns a clean 503 with the exact
commands needed to fix it (`ollama serve`, `ollama pull llama3.1`) rather than a generic 500.

## 4. Production hardening

**Rate limiting (slowapi):** Global default (60/min) plus stricter limits on `/api/auth/*`
(10/min) and `/api/analysis/upload` (10/min) — auth endpoints are the most common target for
credential-stuffing/brute-force, and upload is the most expensive endpoint (CSV parse + model
training), so both get tighter limits than read endpoints.

**Startup safety check:** `main.py` refuses to boot when `ENVIRONMENT=production` and
`SECRET_KEY` is still the shipped placeholder — a JWT signed with a known default key provides
no actual security. This is a five-line check that prevents an entire, silent class of
production misconfiguration.

**Structured logging (`app/logging_config.py`):** Consistent format, one log line per
significant action (register, upload) with the org/user/filename context needed to debug a
production issue without re-running the request.

**Alembic migrations:** Replaced implicit `Base.metadata.create_all()` as the primary schema
mechanism with a real migration (`alembic/versions/0001_initial_schema.py`). `create_all()` is
still called in `main.py` for zero-friction local dev, but the Dockerfile now runs
`alembic upgrade head` before starting the server — the correct pattern once the schema needs
to evolve without dropping data, which `create_all()` cannot do (it only creates tables that
don't exist yet; it never alters existing ones).

**Test suite (21 tests, `backend/tests/`):** Unit tests for the feature engineering/training
pipeline in isolation (`test_pipeline.py`), and integration tests through the actual HTTP layer
for auth, tenant isolation, and both prediction modes. This caught two real bugs during
development — see "What the tests caught" below.

## 5. Frontend

**Auth flow:** `AuthContext`, `ProtectedRoute`, `Login.jsx`, `Register.jsx` — the whole app now
sits behind auth, with an axios interceptor (`api.js`) that attaches the JWT to every request
and auto-redirects to `/login` on a 401 rather than every page handling that individually.

**SHAP display:** The dashboard's high-risk customer table rows expand (click to toggle) to
show the SHAP factor chips for that customer, color-coded by whether the factor increases or
decreases risk. The Prediction page shows the same chips inline under the result, labeled by
whether they came from SHAP (trained model) or the heuristic breakdown (no model trained yet
for this org) — the platform has always been explicit about which mode produced a number, and
that honesty now extends to the explanation too.

**Copilot widget:** A floating chat button (bottom-right, visible on every authenticated page)
that opens a small chat panel scoped to the currently loaded analysis run.

---

## What the tests caught

Writing the test suite surfaced two real bugs before they could ship:

1. **Rate limiting was correctly blocking the test suite itself** — all requests from
   `TestClient` share one pseudo-IP, so the 10/min auth limit tripped after a handful of tests
   in the same session. This is *correct* production behavior (per-IP throttling on auth
   endpoints), so the fix was to raise the limit for the test environment via env vars
   (`tests/conftest.py`), not to weaken the actual rate limit.

2. **Model storage wasn't test-isolated** — trained models are saved to a real path on disk
   keyed by numeric org ID (`storage/models/org_<id>/`), but each test's SQLite database is
   fresh, so org auto-increment IDs restart at 1 every test. A model saved by one test's
   "org 1" was silently picked up by an unrelated later test's "org 1", because the *database*
   was isolated but the *filesystem* wasn't. In real Postgres this can't happen (IDs are never
   reused across the app's lifetime), but it was a legitimate gap in the test harness that the
   fix (`monkeypatch` the model directory to a fresh temp path per test) makes explicit and
   permanent, rather than something that could quietly mask a real bug in a future refactor.

## Before deploying this to production

1. Generate a real `SECRET_KEY` (`python -c "import secrets; print(secrets.token_hex(32))"`)
   and set `ENVIRONMENT=production` — the app will refuse to start otherwise.
2. Decide where Ollama runs in production. A single Render/Fly.io box running both the API and
   an Ollama model is the cheapest option for a demo-scale deployment; for real usage, Ollama
   should run on its own host/GPU instance with `OLLAMA_BASE_URL` pointed at it, or `LLM_PROVIDER`
   swapped to a paid API provider for better throughput and quality.
3. Run `alembic upgrade head` against the production database before first deploy (the
   Dockerfile does this automatically on container start).
4. Reconsider the registration flow's "first user for an org name = owner" pattern before
   opening signups publicly — it has no verification that the person registering actually
   represents that organization. Fine for an internal tool or invite-only pilot; not fine for
   open self-serve signup without an invite-code or email-domain check added first.
5. `storage/models/` and `storage/uploads/` are local filesystem paths — on Render (ephemeral
   filesystem) these will NOT survive a redeploy. Move to S3/GCS-backed storage before relying
   on trained models persisting across deploys.
