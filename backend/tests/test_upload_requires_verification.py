"""Unverified accounts can log in and view past results, but can't start
new analyses — see deps.require_verified for the reasoning."""


def _verify(client, token):
    from app.models_db import User
    user_id = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["id"]
    db = client.db_session_factory()
    try:
        db.query(User).filter(User.id == user_id).update({"is_verified": 1})
        db.commit()
    finally:
        db.close()


def _unverify(client, token):
    from app.models_db import User
    user_id = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["id"]
    db = client.db_session_factory()
    try:
        db.query(User).filter(User.id == user_id).update({"is_verified": 0})
        db.commit()
    finally:
        db.close()


def test_unverified_user_cannot_upload(client, synthetic_churn_csv):
    res = client.post("/api/auth/register", json={
        "email": "unverified@acme.com", "password": "testpassword123",
        "full_name": "U", "organization_name": "UnverifiedOrg",
    })
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

    upload = client.post(
        "/api/analysis/upload",
        files={"file": ("data.csv", synthetic_churn_csv, "text/csv")},
        headers=headers,
    )
    assert upload.status_code == 403
    assert "verify your email" in upload.json()["detail"].lower()


def test_verified_user_can_upload(client, synthetic_churn_csv):
    res = client.post("/api/auth/register", json={
        "email": "willverify@acme.com", "password": "testpassword123",
        "full_name": "V", "organization_name": "WillVerifyOrg",
    })
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    _verify(client, token)

    upload = client.post(
        "/api/analysis/upload",
        files={"file": ("data.csv", synthetic_churn_csv, "text/csv")},
        headers=headers,
    )
    assert upload.status_code == 202


def test_unverified_user_can_still_view_past_runs(client, auth_headers, synthetic_churn_csv):
    """The gate blocks NEW analyses, not access to results a user already
    has — an unverified user isn't locked out of the whole product."""
    headers = auth_headers(email="viewer@acme.com", org="ViewerOrg")  # auth_headers auto-verifies
    token = headers["Authorization"].split(" ")[1]

    upload = client.post(
        "/api/analysis/upload",
        files={"file": ("data.csv", synthetic_churn_csv, "text/csv")},
        headers=headers,
    )
    job = client.get(f"/api/analysis/jobs/{upload.json()['id']}", headers=headers).json()
    run_id = job["analysis_run_id"]

    # Flip the account back to unverified after the fact, and confirm
    # read access to the already-created run still works.
    _unverify(client, token)

    res = client.get(f"/api/analysis/runs/{run_id}", headers=headers)
    assert res.status_code == 200
