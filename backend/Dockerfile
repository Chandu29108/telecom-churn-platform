FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 + scientific stack
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user. Without this the process (and anything an
# attacker gets via a future dependency RCE) runs as root inside the
# container, which is a meaningfully larger blast radius for no benefit —
# nothing here needs root. storage/ has to be created and chown'd before
# switching users since config.py writes model/upload artifacts there.
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/storage/models /app/storage/uploads \
    && chown -R appuser:appuser /app
USER appuser

# Render provides $PORT at runtime; default to 8000 for local/docker-compose.
ENV PORT=8000
EXPOSE 8000

# Lets the orchestrator (Render, `docker compose ps`, Kubernetes, etc.)
# detect a hung/crashed process instead of routing traffic to it forever.
# Uses Python rather than curl/wget so no extra package has to be installed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\",8000)}/api/health', timeout=3)" || exit 1

# Apply pending Alembic migrations, then start the API. `alembic upgrade
# head` is idempotent (no-op if already current) so this is safe to run on
# every container start, including scaled-out replicas.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
