# Deployment Guide

Backend → **Render**. Database → **Neon** (Postgres-compatible, free tier includes point-in-time
recovery — see the production-readiness audit, Phase 7, for why Render's own free Postgres was
rejected: it auto-deletes after 30-90 days with no backups). Frontend → **Vercel**. Model storage
→ **Cloudflare R2**. Error tracking → **Sentry**. LLM copilot → **Groq** (OpenAI-compatible).

> ⚠️ **Known limitation, deliberately deferred:** `EMAIL_PROVIDER` is set to `console` below,
> meaning verification/password-reset emails are logged to Render's server logs, not actually
> sent. This means **real strangers cannot complete registration** — only you, checking the
> Render logs, can retrieve a verification link. This was a deliberate choice to deploy now and
> add real email once a custom domain is purchased (Resend, like every transactional email
> provider, requires a verified domain to send to anyone other than your own account — see the
> "Email verification" section at the bottom for the follow-up steps once you're ready).

## 0. Accounts you need before starting (all free tier)

| Service | What it's for | Where |
|---|---|---|
| Neon | Postgres database | https://neon.tech |
| Render | Backend hosting | https://render.com |
| Vercel | Frontend hosting | https://vercel.com |
| Cloudflare R2 | Trained model storage | https://dash.cloudflare.com |
| Groq | LLM copilot | https://console.groq.com |
| Sentry | Error tracking | https://sentry.io |

## 1. Database (Neon) — do this first

You should already have this from Phase 7: a Neon project with a connection string. Grab it from
the Neon dashboard's "Connect" button, and edit the scheme from `postgresql://` to
`postgresql+psycopg2://` (SQLAlchemy needs the driver suffix). Keep `?sslmode=require` or
`&channel_binding=require` at the end exactly as Neon gives it to you.

Run migrations against it once, from your local machine, before the backend ever boots in
production:
```bash
cd backend
# set DATABASE_URL to your Neon connection string for this one command
alembic upgrade head
```

## 2. Backend (Render)

1. Push this repo to GitHub (should already be done from Phase 2's CI setup).
2. In Render: **New → Web Service** → connect the repo → root directory `backend/`.
   - Environment: **Docker** (Render uses `backend/Dockerfile`).
3. Set these environment variables in Render's dashboard:

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `SECRET_KEY` | Generate with `python -c "import secrets; print(secrets.token_hex(32))"` — **not** the dev placeholder, the app refuses to boot in production with it |
| `DATABASE_URL` | Your Neon connection string (see step 1) |
| `CORS_ORIGINS` | `https://<your-vercel-app>.vercel.app` (fill in after step 3, see step 4) |
| `FRONTEND_URL` | Same Vercel URL — used to build links inside emails |
| `LLM_PROVIDER` | `openai` |
| `OPENAI_API_KEY` | Your Groq API key |
| `R2_BUCKET_NAME` | Your R2 bucket name |
| `R2_ACCOUNT_ID` | Your Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | Your R2 access key |
| `R2_SECRET_ACCESS_KEY` | Your R2 secret key |
| `SENTRY_DSN` | Your Sentry project DSN |
| `EMAIL_PROVIDER` | `console` (see the limitation note at the top — revisit once you have a domain) |

Leave `OPENAI_BASE_URL` / `OPENAI_MODEL` unset — they default correctly to Groq already.

4. Deploy. Confirm `https://<your-service>.onrender.com/api/health` returns `{"status": "ok"}`.
5. Watch the boot logs for the two Phase 3 startup warnings — with the table above filled in
   correctly, **neither should appear**. If you see the Ollama or R2 warning, double-check the
   corresponding env vars above.

> Render's free tier spins down after inactivity — the first request after idle will be slow
> (cold start). Fine while validating the deploy; worth a paid tier before real customer traffic.

## 3. Frontend (Vercel)

1. In Vercel: **New Project** → import the repo → root directory `frontend/`.
2. Framework preset: **Vite**.
3. Environment variable: `VITE_API_BASE_URL` = `https://<your-service>.onrender.com`.
4. Deploy. Vercel auto-detects `vercel.json` for SPA routing (so `/dashboard`, `/insights` etc.
   don't 404 on refresh).

## 4. Reconnect CORS

Now that you have the real Vercel URL, go back to Render's `CORS_ORIGINS` env var and set it
precisely (no trailing slash) — this is the most common cause of "upload works locally but fails
in production." Redeploy the backend after changing it.

## 5. Smoke test

1. Visit your Vercel URL, register an account (you — this is the one account that works given the
   email limitation above), and confirm you land on the dashboard.
2. Check your Render service logs for the printed verification link (same format as local dev's
   console-provider output) and use it to verify your account.
3. Upload a CSV, confirm training completes and the dashboard populates.
4. Try the copilot — confirm it responds via Groq, not an Ollama error.
5. Check your Sentry dashboard — confirm no unexpected errors showed up during the smoke test.

## 6. Uptime monitoring (do this once the URL above is live)

Set up a free external check (Better Stack, UptimeRobot, or similar) pinging
`https://<your-service>.onrender.com/api/health` every few minutes. This is the piece that was
deferred during Phase 7 specifically because it needs a real, live URL to point at.

## 7. Email verification — the follow-up once you have a domain

When you're ready to accept real signups:
1. Buy a domain (Cloudflare Registrar or Porkbun, ~$10/yr — see the audit conversation for why).
2. In Resend, go to **Domains** → add your domain → add the SPF/DKIM DNS records it gives you at
   your registrar → wait for verification (usually minutes).
3. In Render, update env vars: `EMAIL_PROVIDER=resend`, `RESEND_API_KEY=...`,
   `EMAIL_FROM_ADDRESS=noreply@yourdomain.com`.
4. Redeploy. Register a fresh test account with a *different* real email address you control to
   confirm delivery actually works end-to-end before opening registration to the public.

## Local parity with Docker

```bash
docker compose up --build
```

Runs Postgres, the FastAPI backend, and an nginx-served frontend build together, so you can
verify container behavior before pushing. Note: this uses local Postgres, not Neon — fine for
container-level testing, not a substitute for the smoke test against the real deploy above.
