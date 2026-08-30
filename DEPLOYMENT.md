# Deployment Guide

Backend + database → **Render**. Frontend → **Vercel**. This split is chosen because Render
gives you a managed Postgres instance and a Docker-friendly web service in one place, while
Vercel is the fastest path for a static Vite build with automatic preview deployments per PR.

## 1. Database + Backend (Render)

1. Push this repo to GitHub.
2. In Render: **New → PostgreSQL** → note the internal `Connection String`.
3. **New → Web Service** → connect the repo → root directory `backend/`.
   - Environment: **Docker** (Render will use `backend/Dockerfile`).
   - Environment variables:
     - `DATABASE_URL` = the Postgres internal connection string from step 2, with the driver
       prefix changed to `postgresql+psycopg2://...` (Render gives you `postgresql://...` by
       default — SQLAlchemy needs the `+psycopg2` part).
     - `CORS_ORIGINS` = `https://<your-vercel-app>.vercel.app`
     - `CHURN_THRESHOLD` = `0.45` (optional, defaults to this)
4. Deploy. Confirm `https://<your-service>.onrender.com/api/health` returns `{"status": "ok"}`.

> Render's free tier spins down after inactivity — the first request after idle will be slow
> (cold start). Fine for a portfolio demo; upgrade the plan for anything else.

## 2. Frontend (Vercel)

1. In Vercel: **New Project** → import the repo → root directory `frontend/`.
2. Framework preset: **Vite**.
3. Environment variable: `VITE_API_BASE_URL` = `https://<your-service>.onrender.com`.
4. Deploy. Vercel auto-detects `vercel.json` for SPA routing (so `/dashboard`, `/insights` etc.
   don't 404 on refresh).

## 3. Reconnect CORS

Once you have the real Vercel URL, go back to the Render backend's `CORS_ORIGINS` env var and
set it precisely (no trailing slash) — this is the most common cause of "upload works locally
but fails in production."

## 4. Local parity with Docker

```bash
docker compose up --build
```

This runs Postgres, the FastAPI backend, and an nginx-served frontend build together, so you can
verify the exact production container images before pushing.

## 5. Database migrations

This project uses `Base.metadata.create_all()` on startup for simplicity — fine for a portfolio
project with two tables. If you extend the schema later, switch to
[Alembic](https://alembic.sqlalchemy.org/) migrations rather than relying on auto-create.
