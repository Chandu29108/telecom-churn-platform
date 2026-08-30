"""Personal (single-seat) vs organization (multi-seat) account types."""


def test_personal_signup_does_not_require_organization_name(client):
    res = client.post("/api/auth/register", json={
        "email": "solo@example.com", "password": "testpassword123",
        "full_name": "Solo User", "account_type": "personal",
    })
    assert res.status_code == 201, res.text
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {res.json()['access_token']}"}).json()
    assert me["account_type"] == "personal"
    assert "Solo User" in me["organization_name"]  # auto-generated workspace name


def test_organization_signup_still_requires_organization_name(client):
    res = client.post("/api/auth/register", json={
        "email": "noorg@example.com", "password": "testpassword123",
        "full_name": "No Org", "account_type": "organization",
    })
    assert res.status_code == 400
    assert "organization name is required" in res.json()["detail"].lower()


def test_two_personal_signups_with_same_display_name_dont_collide(client):
    """Organization.name is globally unique, but personal workspace names
    are auto-generated from full_name and easily collide across
    different real people — must not 500 on the second one."""
    for email in ("dup1@example.com", "dup2@example.com"):
        res = client.post("/api/auth/register", json={
            "email": email, "password": "testpassword123",
            "full_name": "Same Name", "account_type": "personal",
        })
        assert res.status_code == 201, res.text


def test_personal_account_cannot_create_invites(client):
    res = client.post("/api/auth/register", json={
        "email": "soloowner@example.com", "password": "testpassword123",
        "full_name": "Solo Owner", "account_type": "personal",
    })
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

    invite_res = client.post("/api/auth/invites", json={}, headers=headers)
    assert invite_res.status_code == 400
    assert "single-seat" in invite_res.json()["detail"].lower()


def test_personal_account_has_lower_upload_row_cap(client, synthetic_churn_csv, monkeypatch):
    import app.routers.analysis as analysis_router
    # Lower the personal cap below the synthetic fixture's 200 rows so the
    # test doesn't need a huge CSV to exercise the limit.
    from app.models_db import Organization

    res = client.post("/api/auth/register", json={
        "email": "smallcap@example.com", "password": "testpassword123",
        "full_name": "Small Cap", "account_type": "personal",
    })
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from app.models_db import User
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]
    db = client.db_session_factory()
    try:
        db.query(User).filter(User.id == user_id).update({"is_verified": 1})
        org_id = db.query(User).filter(User.id == user_id).first().org_id
        db.query(Organization).filter(Organization.id == org_id).update({"max_upload_rows": 100})
        db.commit()
    finally:
        db.close()

    upload = client.post(
        "/api/analysis/upload", headers=headers,
        files={"file": ("churn.csv", synthetic_churn_csv, "text/csv")},  # 200 rows > 100 cap
    )
    job_id = upload.json()["id"]
    job = client.get(f"/api/analysis/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "FAILED"
    assert "exceeds the current limit" in job["error_message"]


def test_organization_account_unaffected_by_personal_cap(client, auth_headers, synthetic_churn_csv):
    """Sanity check: a normal organization account's upload (200 rows,
    well under the global default) still works exactly as before —
    org.max_upload_rows is NULL for it, so the global MAX_UPLOAD_ROWS
    default applies, same as pre-account-types behaviour."""
    headers = auth_headers(email="normalorg@example.com", org="Normal Org")
    upload = client.post(
        "/api/analysis/upload", headers=headers,
        files={"file": ("churn.csv", synthetic_churn_csv, "text/csv")},
    )
    job = client.get(f"/api/analysis/jobs/{upload.json()['id']}", headers=headers).json()
    assert job["status"] == "COMPLETED"
