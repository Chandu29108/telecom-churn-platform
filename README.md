# 📡 Telecom Churn Intelligence Platform

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.5-F7931E?logo=scikitlearn&logoColor=white)
![SHAP](https://img.shields.io/badge/Explainability-SHAP-8A2BE2)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

An end-to-end, **multi-tenant** churn prediction platform: upload telecom usage data, and it
trains a Gradient Boosting model, scores every customer into risk tiers with a **SHAP-explained
reason for each score**, and generates a live dashboard, business insights, and retention
recommendations — plus a local LLM copilot to ask questions about the results in plain English.

**This is not a static portfolio page.** The analysis notebook (`notebook/main.ipynb`) is the
research artifact; the web app is the same pipeline turned into an operational, org-scoped SaaS
tool that produces fresh, explainable results for whatever dataset your organization gives it.

---

## What's new in v2.0

A full market-research pass (see `docs/market_research.md` if you keep it alongside this repo)
found the platform's core ML loop (upload → train → dashboard) was already table stakes against
funded competitors like Pecan AI, DataRobot, and H2O.ai — and that **explainability, auth, and
an LLM layer were the gaps that mattered most**. This release closes them:

- **Multi-tenant auth (JWT)** — every organization's uploads, trained models, and analysis
  history are isolated from every other organization's. First person to register an org name
  becomes its owner; teammates who register with the same org name join it.
- **SHAP explainability** — the dashboard's high-risk customer table and the single-customer
  Prediction page now show *why* each score is what it is (top contributing features, signed,
  with direction), not just the number.
- **LLM copilot** — a chat widget that answers questions about the current analysis run
  ("which risk tier should we target first?"), grounded strictly in that run's own numbers.
  Runs on a free local Ollama model by default — no API key required — via a pluggable provider
  interface so a paid provider can be swapped in later with a one-line config change.
- **Production hardening** — rate limiting, structured logging, Alembic migrations (replacing
  implicit `create_all`), a startup check that refuses to boot in production with a default
  secret key, and a real pytest suite (21 tests: auth, tenant isolation, pipeline, SHAP, both
  prediction modes).

## What's inside

| Path | What it is |
|---|---|
| `notebook/` | The original EDA + model-development notebook (99,999 customers, 11 models compared, Gradient Boosting selected — ROC-AUC 0.946) |
| `docs/01_business_insights_and_recommendations.md` | Written business insights & recommendations, grounded in the notebook's actual output |
| `docs/dashboard_spec.md` | Power BI–ready dashboard spec: fields, DAX measures, layout, wireframe |
| `docs/CHANGELOG_v2.md` | Full explanation of every v2 change and the reasoning behind it |
| `backend/` | FastAPI service — auth, feature engineering, model training/scoring, SHAP explainability, LLM copilot, insight generation, Postgres persistence |
| `backend/tests/` | Pytest suite covering auth, tenant isolation, the ML pipeline, and both prediction modes |
| `backend/alembic/` | Database migrations |
| `frontend/` | React + Vite + Tailwind app — login/register, upload flow, dashboard (with SHAP), insights, recommendations, single-customer prediction (with SHAP), copilot chat |
| `docker-compose.yml` | One-command local dev environment (Postgres + backend + frontend) |

## Architecture

```
 ┌────────────┐      CSV upload        ┌──────────────┐      SQL        ┌────────────┐
 │  React SPA │ ────────────────────▶ │   FastAPI     │ ──────────────▶ │ PostgreSQL │
 │ (Vercel)   │ ◀──────────────────── │   (Render)    │ ◀────────────── │  (Render)  │
 └─────┬──────┘   dashboard + SHAP     └──────┬───────┘   scores/users   └────────────┘
       │           JSON (JWT-authed)          │
       │                              feature engineering
       │                              + Gradient Boosting
       │                              + SHAP TreeExplainer
       ▼                              (scikit-learn, shap, joblib — per-org model files)
 ┌────────────┐    chat over results   ┌──────────────┐
 │  Copilot   │ ─────────────────────▶ │  Ollama (local) │  ← pluggable: swap for a paid LLM later
 │  widget    │ ◀───────────────────── │  (free, no key)  │
 └────────────┘
```

## Why these choices

- **Gradient Boosting**, not the fanciest model available: the source notebook compared 11
  models and it won on ROC-AUC (0.946) *and* had the best cross-validated stability
  (0.9428 ± 0.0046) — a defensible choice, not a default one.
- **Re-fit on upload rather than one frozen model**: churn behaviour differs by operator and
  time period. The backend re-runs the notebook's exact feature engineering + training logic on
  whatever you upload, scoped to your organization, so results reflect your data.
- **SHAP over "trust the model"**: a churn score with no reason attached is unactionable for a
  retention team and is the single feature gap that separates this platform from every serious
  funded competitor (DataRobot, H2O.ai, Kumo.ai all have it). TreeExplainer gives exact, fast
  per-customer contributions for tree ensembles like this one — only computed for the customers
  actually shown (top 50 on the dashboard, 1 on the Prediction page), never the full dataset, to
  keep it fast.
- **Local Ollama copilot, not a paid API by default**: keeps the feature demoable and free for
  anyone cloning this repo, and the provider is abstracted (`app/llm/`) so swapping to a paid
  model later is a one-line config change, not a rewrite.
- **Insights are rule-generated, not LLM-generated**: deterministic, instant, and free per
  request for the dashboard's automated insights — the LLM is reserved for the copilot's
  open-ended Q&A, where its flexibility actually earns its cost/latency.
- **No fake live Power BI embed**: a real embedded Power BI report needs your own Power BI
  Service workspace. Instead, the web app *is* the interactive dashboard, and `docs/dashboard_spec.md`
  gives you everything needed to point Power BI Desktop at the same Postgres tables for a second,
  "official BI tool" version of the same numbers.

## Quickstart (local, Docker)

```bash
git clone <your-repo-url>
cd telecom-churn-platform
docker compose up --build
# frontend → http://localhost:5173
# backend  → http://localhost:8000/docs   (interactive API docs)
```

The copilot needs a local Ollama server reachable from the backend container. On the host:

```bash
# https://ollama.com/download
ollama serve
ollama pull llama3.1        # or a smaller model, e.g. `ollama pull llama3.2:1b`, then set
                             # OLLAMA_MODEL accordingly in backend/.env / docker-compose.yml
```

Everything else (auth, SHAP, dashboards) works without Ollama running — only `/api/copilot`
needs it, and it fails with a clear, actionable error message if it's not reachable.

## Quickstart (without Docker)

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt                # includes pytest; use requirements.txt for prod-only
cp .env.example .env   # point DATABASE_URL at a local Postgres, or use SQLite for a quick test
alembic upgrade head    # create/upgrade the schema
uvicorn app.main:app --reload

# run the test suite
pytest

# Frontend (separate terminal)
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

First run: open the frontend, click **Create one** on the login screen, register your
organization, then upload a dataset from the Upload page.

## Deployment

See [`DEPLOYMENT.md`](./DEPLOYMENT.md) for the full Render (backend + Postgres) + Vercel
(frontend) guide, and [`docs/CHANGELOG_v2.md`](./docs/CHANGELOG_v2.md) for the production
checklist (secret key, migrations, rate limits, Ollama hosting options) before deploying v2.

## Model performance (source notebook)

| Model | ROC-AUC | F1 | Recall |
|---|---|---|---|
| **Gradient Boosting** ✅ | **0.9461** | 0.6263 | 0.8492 |
| GB Tuned | 0.9458 | 0.6332 | 0.8420 |
| LightGBM | 0.9454 | 0.6327 | 0.8409 |
| Voting Ensemble | 0.9439 | 0.6833 | 0.7578 |
| Random Forest | 0.9404 | 0.6686 | 0.7594 |
| Logistic Regression | 0.9245 | 0.5402 | 0.8409 |

5-fold CV: **0.9428 ± 0.0046 AUC** — full comparison in the notebook.

## Resume-ready description

> **Telecom Churn Intelligence Platform** — Built a multi-tenant, explainable churn prediction
> SaaS platform (React/FastAPI/PostgreSQL) with JWT auth, a Gradient Boosting model (ROC-AUC
> 0.946, 85% recall), SHAP-based per-customer explanations, and a local-LLM copilot for
> plain-English Q&A over results.
> - Engineered 169 features (trend, ratio, and behavioural signals) from 226 raw telecom usage
>   fields; compared 11 classifiers and selected by cross-validated ROC-AUC + recall trade-off.
> - Added SHAP (TreeExplainer) per-customer explainability, scoped to only the customers shown
>   in the UI to keep explanation latency low on a 100K+ row dataset.
> - Designed a JWT-based multi-tenant architecture (org-scoped data, models, and API access) with
>   rate limiting, structured logging, and Alembic-managed schema migrations.
> - Built a pluggable LLM provider abstraction and wired a local-Ollama-backed copilot that
>   answers questions strictly from the current analysis run's stored results.
> - Shipped a containerized, three-tier architecture (React/Vite → FastAPI → PostgreSQL) deployed
>   on Vercel + Render with Docker for local parity, backed by a 21-test pytest suite covering
>   auth, tenant isolation, and the ML pipeline.

## Future improvements

- Swap the on-upload training with a scheduled retraining job + model registry (e.g. MLflow) once
  there's a real production data feed.
- Real CRM/billing/support integrations (beyond CSV upload) for a Next-Best-Offer recommendation
  engine tied to specific retention actions.
- Real-time/streaming scoring (Kafka-based ingestion) instead of batch-only CSV upload.
- SOC 2 / audit-log posture and SSO if pursuing an actual enterprise telecom buyer.

## License

MIT — see `LICENSE`.
