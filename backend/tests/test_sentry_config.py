"""Sentry must never initialize during automated test runs, even if a real
SENTRY_DSN happens to be sitting in .env (loaded the same way for `pytest`
as for `uvicorn`) — otherwise every test run reports its own deliberately-
thrown test exceptions to Sentry as if they were real incidents. This
happened for real during manual Phase 7 verification, which is why this
test exists: app/main.py's import-time guard is what's being tested here,
so it has to run in a fresh subprocess rather than through the shared
`client` fixture (the app module is only ever imported once per process).
"""
import subprocess
import sys
import tempfile
import os

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_app_import_in_subprocess(environment: str) -> subprocess.CompletedProcess:
    """Imports app.main in a clean subprocess with the given ENVIRONMENT
    and a fake SENTRY_DSN, then reports whether sentry_sdk ended up loaded.

    Uses mkstemp() + an immediate os.close() rather than
    tempfile.NamedTemporaryFile — NamedTemporaryFile keeps its own file
    handle open in this (the pytest) process for the duration of the
    `with` block, and Windows (unlike Linux/Mac) won't let a *different*
    process's SQLite driver open that same file while it's held open,
    which made every subprocess crash before printing anything. Same root
    cause, same fix, as the Phase 1 conftest.py Windows teardown fix.
    """
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    try:
        env = os.environ.copy()
        env.update({
            "ENVIRONMENT": environment,
            "SENTRY_DSN": "https://fake-key@fake-org.ingest.sentry.io/12345",
            "DATABASE_URL": f"sqlite:///{db_path}",
            "EMAIL_PROVIDER": "console",
        })
        return subprocess.run(
            [sys.executable, "-c",
             "import app.main; import sys; "
             "print('SENTRY_LOADED' if 'sentry_sdk' in sys.modules else 'SENTRY_NOT_LOADED')"],
            env=env, capture_output=True, text=True, timeout=30, cwd=BACKEND_DIR,
        )
    finally:
        try:
            os.remove(db_path)
        except PermissionError:
            pass


def test_sentry_never_initializes_when_environment_is_test():
    result = _run_app_import_in_subprocess("test")
    assert "SENTRY_NOT_LOADED" in result.stdout, (
        f"Sentry initialized during ENVIRONMENT=test — this would report "
        f"test exceptions as real incidents. stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_sentry_does_initialize_outside_test_environment_when_dsn_set():
    """The flip side — make sure the fix above didn't just disable Sentry
    entirely. It should still initialize normally in development/production
    when a DSN is present."""
    result = _run_app_import_in_subprocess("development")
    assert "SENTRY_LOADED" in result.stdout, (
        f"Sentry should initialize outside ENVIRONMENT=test when a DSN is set. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
