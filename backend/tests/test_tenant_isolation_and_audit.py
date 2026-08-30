"""IDOR / cross-org regression tests (audit report, Part 6 — flags the
existing org_id-filtering pattern as correct but calls for explicit
regression coverage as new endpoints are added) plus a smoke test for the
new audit-log viewer endpoint."""


def _register(client, email, org):
    res = client.post("/api/auth/register", json={
        "email": email, "password": "testpassword123",
        "full_name": "T", "organization_name": org,
    })
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]

    from app.models_db import User
    user_id = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["id"]
    db = client.db_session_factory()
    try:
        db.query(User).filter(User.id == user_id).update({"is_verified": 1})
        db.commit()
    finally:
        db.close()

    return {"Authorization": f"Bearer {token}"}


def test_org_a_cannot_read_org_b_run(client, synthetic_churn_csv):
    headers_a = _register(client, "a@iso.com", "IsoOrgA")
    headers_b = _register(client, "b@iso.com", "IsoOrgB")

    upload = client.post(
        "/api/analysis/upload",
        files={"file": ("data.csv", synthetic_churn_csv, "text/csv")},
        headers=headers_a,
    )
    assert upload.status_code == 202
    job = client.get(f"/api/analysis/jobs/{upload.json()['id']}", headers=headers_a).json()
    assert job["status"] == "COMPLETED"
    run_id = job["analysis_run_id"]

    # Org A can read its own run.
    own = client.get(f"/api/analysis/runs/{run_id}", headers=headers_a)
    assert own.status_code == 200

    # Org B must NOT be able to read org A's run by guessing/incrementing the id.
    cross = client.get(f"/api/analysis/runs/{run_id}", headers=headers_b)
    assert cross.status_code == 404


def test_org_a_cannot_activate_org_b_model_version(client, synthetic_churn_csv):
    headers_a = _register(client, "owner_a@iso2.com", "IsoOrgA2")
    headers_b = _register(client, "owner_b@iso2.com", "IsoOrgB2")

    client.post(
        "/api/analysis/upload",
        files={"file": ("data.csv", synthetic_churn_csv, "text/csv")},
        headers=headers_a,
    )

    # Org B tries to activate version 1 (which belongs to org A, not B).
    res = client.post("/api/analysis/models/1/activate", headers=headers_b)
    assert res.status_code == 404


def test_org_a_cannot_see_org_b_audit_logs(client):
    headers_a = _register(client, "aud_a@iso3.com", "IsoOrgA3")
    _register(client, "aud_b@iso3.com", "IsoOrgB3")

    res = client.get("/api/audit", headers=headers_a)
    assert res.status_code == 200
    body = res.json()
    # Every returned event must belong to org A's own account-creation
    # event, never org B's.
    emails_in_metadata = [
        e.get("metadata_", {}) for e in body if e.get("metadata_")
    ]
    assert all("aud_b" not in str(m) for m in emails_in_metadata)


def test_non_owner_cannot_view_audit_logs(client):
    owner_headers = _register(client, "owner_c@iso4.com", "IsoOrgC")
    invite = client.post("/api/auth/invites", json={}, headers=owner_headers)
    member_headers = {
        "Authorization": f"Bearer {client.post('/api/auth/register', json={'email': 'member_c@iso4.com', 'password': 'testpassword123', 'full_name': 'M', 'organization_name': 'IsoOrgC', 'invite_token': invite.json()['token']}).json()['access_token']}"
    }
    res = client.get("/api/audit", headers=member_headers)
    assert res.status_code == 403


def test_audit_log_records_login_events(client):
    headers = _register(client, "auditme@example.com", "AuditOrg")
    client.post("/api/auth/login", data={"username": "auditme@example.com", "password": "testpassword123"})

    res = client.get("/api/audit", headers=headers)
    assert res.status_code == 200
    event_types = {e["event_type"] for e in res.json()}
    assert "auth.login" in event_types
    assert "account.created" in event_types
