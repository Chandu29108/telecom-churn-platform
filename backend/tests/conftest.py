"""
Every test gets a fresh, isolated SQLite database (file per test run,
deleted after) via dependency override on get_db — no shared state between
tests, and no need for a real Postgres instance to run the suite.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-not-for-production")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_unused_by_tests.db")
# The rate limiter keys on client IP, and TestClient sends every request
# from the same pseudo-IP ("testclient"). Production's 10/minute auth limit
# is correct there (see it trip in test_analysis.py's isolation tests if you
# lower this) but would make the *test suite itself* flaky/order-dependent,
# so tests run against a much higher limit instead of disabling the feature.
os.environ.setdefault("RATE_LIMIT_DEFAULT", "10000/minute")
os.environ.setdefault("RATE_LIMIT_UPLOAD", "10000/minute")
os.environ.setdefault("RATE_LIMIT_AUTH", "10000/minute")

from app.main import app  # noqa: E402
from app.database import Base, get_db  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Trained models are stored on disk per-org (storage/models/org_<id>/).
    # Each test gets a fresh SQLite DB where org auto-increment IDs restart
    # at 1, but the real filesystem persists across tests — without this,
    # a model saved by an earlier test's "org_1" would leak into a later
    # test's unrelated "org_1". Point both routers at an isolated tmp dir
    # per test so model storage has the same isolation the DB does.
    import app.routers.analysis as analysis_router
    import app.routers.prediction as prediction_router
    monkeypatch.setattr(analysis_router, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(prediction_router, "MODEL_DIR", tmp_path)
    # Background jobs (Phase 2) run outside the request-scoped `db`
    # session and open their own via app.routers.analysis.SessionLocal —
    # point that at the same per-test SQLite engine as get_db, and point
    # UPLOAD_DIR at the same isolated tmp_path so job temp files don't
    # leak between tests either.
    monkeypatch.setattr(analysis_router, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(analysis_router, "UPLOAD_DIR", tmp_path)

    # raise_server_exceptions=False: a real client only ever sees the HTTP
    # response, never the Python exception — this makes the test suite
    # exercise the actual global exception handler (see
    # test_error_handling.py) instead of pytest re-raising the traceback.
    with TestClient(app, raise_server_exceptions=False) as c:
        # Exposes the same session factory the app itself uses, so tests
        # that need to reach into the DB directly (e.g. to read a
        # verification/reset token that would normally only ever be
        # emailed, never returned over the API) can do so without a
        # second, divergent DB connection.
        c.db_session_factory = TestingSessionLocal
        yield c

    app.dependency_overrides.clear()
    # Windows holds an open file handle on a SQLite db file until every
    # connection in the engine's pool is explicitly closed — Linux/Mac
    # don't enforce this, which is why this only ever showed up running
    # the suite on Windows. Dispose the engine (closes pooled connections)
    # before trying to delete the file; if some other pooled connection
    # (e.g. one left dangling by an errored test) is still holding it
    # open, don't fail an otherwise-passing test over a leftover temp
    # file the OS will clean up on its own anyway.
    engine.dispose()
    os.close(db_fd)
    try:
        os.remove(db_path)
    except PermissionError:
        pass


@pytest.fixture()
def auth_headers(client):
    """Registers a fresh user/org and returns ready-to-use auth headers.
    Marks the account verified directly in the DB — most tests aren't
    about the verification flow itself (that's covered explicitly in
    test_email_verification_and_reset.py and
    test_upload_requires_verification.py) and upload/retry now require a
    verified account (see deps.require_verified), so leaving every fixture
    user unverified would make nearly every analysis test fail for an
    unrelated reason."""
    def _make(email="user@example.com", org="Test Org"):
        res = client.post("/api/auth/register", json={
            "email": email,
            "password": "testpassword123",
            "full_name": "Test User",
            "organization_name": org,
        })
        assert res.status_code == 201, res.text
        token = res.json()["access_token"]

        # Look the user up by id (via /me) rather than by the raw email
        # string — pydantic's EmailStr lowercases the domain on the way
        # in, so the row in the DB may not match the exact case the
        # caller passed here.
        from app.models_db import User
        user_id = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["id"]
        db = client.db_session_factory()
        try:
            db.query(User).filter(User.id == user_id).update({"is_verified": 1})
            db.commit()
        finally:
            db.close()

        return {"Authorization": f"Bearer {token}"}
    return _make


@pytest.fixture()
def synthetic_churn_csv():
    """Builds an in-memory CSV matching the schema pipeline.py expects
    (month-suffixed usage/recharge/ARPU columns), with a deliberate churn
    signal so training produces a non-degenerate model."""
    import io
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    n = 200
    df = pd.DataFrame({"mobile_number": 7000000000 + np.arange(n)})
    for m in [6, 7, 8, 9]:
        df[f"total_ic_mou_{m}"] = rng.exponential(80, n)
        df[f"total_og_mou_{m}"] = rng.exponential(90, n)
        df[f"arpu_{m}"] = rng.exponential(150, n)
        df[f"total_rech_amt_{m}"] = rng.exponential(180, n)
        if m == 9:
            df[f"vol_2g_mb_{m}"] = rng.exponential(50, n)
            df[f"vol_3g_mb_{m}"] = rng.exponential(50, n)
    df["aon"] = rng.integers(30, 2000, n)
    df["roam_og_mou_8"] = rng.exponential(5, n)

    churn_idx = rng.choice(n, 40, replace=False)
    for c in ["total_ic_mou_9", "total_og_mou_9", "vol_2g_mb_9", "vol_3g_mb_9"]:
        df.loc[churn_idx, c] = 0

    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return buf.getvalue()
