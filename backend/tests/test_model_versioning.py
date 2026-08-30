"""
Model versioning replaced the old behaviour of unconditionally overwriting
storage/models/org_<id>/latest_model.joblib on every labelled upload. These
tests cover the actual guarantees that change is supposed to provide:
version history exists, it's org-isolated, and an owner can roll back.
"""


def test_second_upload_creates_a_new_active_version(client, auth_headers, synthetic_churn_csv):
    headers = auth_headers()

    first = client.post(
        "/api/analysis/upload", headers=headers,
        files={"file": ("churn1.csv", synthetic_churn_csv, "text/csv")},
    )
    first_job = client.get(f"/api/analysis/jobs/{first.json()['id']}", headers=headers).json()
    assert first_job["status"] == "COMPLETED"

    second = client.post(
        "/api/analysis/upload", headers=headers,
        files={"file": ("churn2.csv", synthetic_churn_csv, "text/csv")},
    )
    second_job = client.get(f"/api/analysis/jobs/{second.json()['id']}", headers=headers).json()
    assert second_job["status"] == "COMPLETED"

    versions = client.get("/api/analysis/models", headers=headers).json()
    assert len(versions) == 2
    active = [v for v in versions if v["is_active"]]
    assert len(active) == 1
    assert active[0]["version"] == 2  # most recent upload is active, old one kept not deleted


def test_model_versions_are_isolated_between_organizations(client, auth_headers, synthetic_churn_csv):
    org_a = auth_headers(email="a@versorga.com", org="Version Org A")
    org_b = auth_headers(email="b@versorgb.com", org="Version Org B")

    client.post(
        "/api/analysis/upload", headers=org_a,
        files={"file": ("churn.csv", synthetic_churn_csv, "text/csv")},
    )

    assert len(client.get("/api/analysis/models", headers=org_a).json()) == 1
    assert len(client.get("/api/analysis/models", headers=org_b).json()) == 0


def test_owner_can_roll_back_to_earlier_version(client, auth_headers, synthetic_churn_csv):
    headers = auth_headers()
    client.post(
        "/api/analysis/upload", headers=headers,
        files={"file": ("churn1.csv", synthetic_churn_csv, "text/csv")},
    )
    client.post(
        "/api/analysis/upload", headers=headers,
        files={"file": ("churn2.csv", synthetic_churn_csv, "text/csv")},
    )

    rollback = client.post("/api/analysis/models/1/activate", headers=headers)
    assert rollback.status_code == 200
    assert rollback.json() == {"version": 1, "is_active": True}

    versions = {v["version"]: v["is_active"] for v in client.get("/api/analysis/models", headers=headers).json()}
    assert versions == {1: True, 2: False}


def test_member_cannot_roll_back_model_version(client, auth_headers):
    """Rollback changes what every user in the org gets scored against —
    same require_owner gate as invite creation."""
    owner_res = client.post("/api/auth/register", json={
        "email": "owner@rollbackorg.com", "password": "testpassword123",
        "full_name": "Owner", "organization_name": "Rollback Org",
    })
    owner_headers = {"Authorization": f"Bearer {owner_res.json()['access_token']}"}
    invite_token = client.post("/api/auth/invites", json={}, headers=owner_headers).json()["token"]

    member_res = client.post("/api/auth/register", json={
        "email": "member@rollbackorg.com", "password": "testpassword123",
        "full_name": "Member", "organization_name": "Rollback Org", "invite_token": invite_token,
    })
    member_headers = {"Authorization": f"Bearer {member_res.json()['access_token']}"}

    res = client.post("/api/analysis/models/1/activate", headers=member_headers)
    assert res.status_code == 403


def test_cannot_activate_another_orgs_model_version(client, auth_headers, synthetic_churn_csv):
    org_a = auth_headers(email="a@rbisoA.com", org="RB Isolation A")
    org_b = auth_headers(email="b@rbisoB.com", org="RB Isolation B")

    client.post(
        "/api/analysis/upload", headers=org_a,
        files={"file": ("churn.csv", synthetic_churn_csv, "text/csv")},
    )  # org A now has version 1

    # org B has no versions at all; trying to activate "version 1" must 404,
    # never affect org A's version 1.
    res = client.post("/api/analysis/models/1/activate", headers=org_b)
    assert res.status_code == 404
