"""Upload -> background job -> result flow (Phase 2: async processing).

TestClient (Starlette) runs FastAPI BackgroundTasks synchronously as part
of the request/response cycle before returning, so in this test suite a
job is already COMPLETED/FAILED by the time the poll call is made — no
sleep/retry loop needed. That's a test-environment property, not a
production one; see routers/analysis.py's module docstring for the real
async behaviour in production.
"""


def _upload(client, headers, filename, content):
    return client.post(
        "/api/analysis/upload", headers=headers,
        files={"file": (filename, content, "text/csv")},
    )


def _upload_and_wait(client, headers, filename, content):
    res = _upload(client, headers, filename, content)
    assert res.status_code == 202, res.text
    job_id = res.json()["id"]
    job = client.get(f"/api/analysis/jobs/{job_id}", headers=headers).json()
    return job


def test_upload_requires_auth(client, synthetic_churn_csv):
    res = client.post(
        "/api/analysis/upload",
        files={"file": ("data.csv", synthetic_churn_csv, "text/csv")},
    )
    assert res.status_code == 401


def test_upload_rejects_non_csv(client, auth_headers):
    headers = auth_headers()
    res = client.post(
        "/api/analysis/upload",
        headers=headers,
        files={"file": ("data.txt", b"not a csv", "text/plain")},
    )
    assert res.status_code == 400


def test_upload_rejects_too_few_rows(client, auth_headers):
    headers = auth_headers()
    tiny_csv = b"mobile_number,arpu_6\n1,10\n2,20\n"
    res = client.post(
        "/api/analysis/upload",
        headers=headers,
        files={"file": ("tiny.csv", tiny_csv, "text/csv")},
    )
    assert res.status_code == 400
    assert "at least 50 rows" in res.json()["detail"]


def test_upload_creates_a_queued_job_immediately(client, auth_headers, synthetic_churn_csv):
    """The request itself must return fast (202 + job id), not block for
    the full training/SHAP pipeline — that's the whole point of Phase 2."""
    headers = auth_headers()
    res = _upload(client, headers, "churn.csv", synthetic_churn_csv)
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["filename"] == "churn.csv"
    assert body["status"] in ("QUEUED", "PROCESSING", "COMPLETED")


def test_upload_rejects_too_many_rows(client, auth_headers, synthetic_churn_csv, monkeypatch):
    # Lower the cap instead of generating a 300k-row CSV so the test stays fast.
    import app.routers.analysis as analysis_router
    monkeypatch.setattr(analysis_router, "MAX_UPLOAD_ROWS", 100)

    headers = auth_headers()
    job = _upload_and_wait(client, headers, "churn.csv", synthetic_churn_csv)  # 200 rows > cap of 100
    assert job["status"] == "FAILED"
    assert "exceeds the current limit" in job["error_message"]


def test_upload_trains_model_and_returns_shap_factors(client, auth_headers, synthetic_churn_csv):
    headers = auth_headers()
    job = _upload_and_wait(client, headers, "churn.csv", synthetic_churn_csv)

    assert job["status"] == "COMPLETED", job
    assert job["row_count"] == 200
    assert job["analysis_run_id"] is not None

    run = client.get(f"/api/analysis/runs/{job['analysis_run_id']}", headers=headers).json()
    assert run["trained"] is True
    assert "roc_auc" in run["metrics"]
    assert len(run["feature_importance"]) > 0
    assert len(run["top_high_risk_customers"]) > 0

    top_customer = run["top_high_risk_customers"][0]
    assert "top_factors" in top_customer
    assert len(top_customer["top_factors"]) > 0
    factor = top_customer["top_factors"][0]
    assert "feature" in factor and "impact" in factor and "direction" in factor
    assert factor["direction"] in ("increases_risk", "decreases_risk")


def test_runs_are_isolated_between_organizations(client, auth_headers, synthetic_churn_csv):
    org1_headers = auth_headers(email="user1@org1.com", org="Org One")
    org2_headers = auth_headers(email="user2@org2.com", org="Org Two")

    _upload_and_wait(client, org1_headers, "churn.csv", synthetic_churn_csv)

    org1_runs = client.get("/api/analysis/runs", headers=org1_headers).json()
    org2_runs = client.get("/api/analysis/runs", headers=org2_headers).json()

    assert len(org1_runs) == 1
    assert len(org2_runs) == 0  # org 2 must NOT see org 1's upload


def test_cannot_fetch_another_orgs_run_by_id(client, auth_headers, synthetic_churn_csv):
    org1_headers = auth_headers(email="user1@orgA.com", org="Org A")
    org2_headers = auth_headers(email="user2@orgB.com", org="Org B")

    job = _upload_and_wait(client, org1_headers, "churn.csv", synthetic_churn_csv)
    run_id = job["analysis_run_id"]

    # org 1 can fetch its own run
    assert client.get(f"/api/analysis/runs/{run_id}", headers=org1_headers).status_code == 200
    # org 2 must get a 404, not org 1's data
    assert client.get(f"/api/analysis/runs/{run_id}", headers=org2_headers).status_code == 404


def test_cannot_fetch_another_orgs_job_by_id(client, auth_headers, synthetic_churn_csv):
    org1_headers = auth_headers(email="user1@orgC.com", org="Org C")
    org2_headers = auth_headers(email="user2@orgD.com", org="Org D")

    res = _upload(client, org1_headers, "churn.csv", synthetic_churn_csv)
    job_id = res.json()["id"]

    assert client.get(f"/api/analysis/jobs/{job_id}", headers=org1_headers).status_code == 200
    assert client.get(f"/api/analysis/jobs/{job_id}", headers=org2_headers).status_code == 404


def test_duplicate_upload_while_job_in_progress_is_rejected(client, auth_headers, synthetic_churn_csv, monkeypatch):
    """Guards against one org stacking up multiple heavy jobs at once
    against the single-process BackgroundTasks threadpool. Since jobs
    complete synchronously within a TestClient request, this test forces
    the first job to stay QUEUED by monkeypatching the processor to a
    no-op, so the second upload sees it still in flight."""
    import app.routers.analysis as analysis_router
    monkeypatch.setattr(analysis_router, "_process_job", lambda job_id: None)

    headers = auth_headers()
    first = _upload(client, headers, "churn1.csv", synthetic_churn_csv)
    assert first.status_code == 202
    assert first.json()["status"] == "QUEUED"

    second = _upload(client, headers, "churn2.csv", synthetic_churn_csv)
    assert second.status_code == 409


def test_retry_failed_job(client, auth_headers, synthetic_churn_csv, monkeypatch):
    import app.routers.analysis as analysis_router
    monkeypatch.setattr(analysis_router, "MAX_UPLOAD_ROWS", 100)  # force failure (200 rows > 100)

    headers = auth_headers()
    job = _upload_and_wait(client, headers, "churn.csv", synthetic_churn_csv)
    assert job["status"] == "FAILED"

    # Raise the cap back up and retry — should now succeed against the
    # same originally-uploaded file, no re-upload needed.
    monkeypatch.setattr(analysis_router, "MAX_UPLOAD_ROWS", 100000)
    retry_res = client.post(f"/api/analysis/jobs/{job['id']}/retry", headers=headers)
    assert retry_res.status_code == 200, retry_res.text
    retried = client.get(f"/api/analysis/jobs/{job['id']}", headers=headers).json()
    assert retried["status"] == "COMPLETED"
    assert retried["retry_count"] == 1
