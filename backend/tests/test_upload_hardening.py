"""File-upload validation added in Phase 1 (audit report, Part 6, finding #7)."""
import io

import pandas as pd


def _auth(client, email="uploader@acme.com", org="UploadOrg"):
    res = client.post("/api/auth/register", json={
        "email": email, "password": "testpassword123",
        "full_name": "U", "organization_name": org,
    })
    from app.models_db import User
    token = res.json()['access_token']
    user_id = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["id"]
    db = client.db_session_factory()
    try:
        db.query(User).filter(User.id == user_id).update({"is_verified": 1})
        db.commit()
    finally:
        db.close()
    return {"Authorization": f"Bearer {token}"}


def test_too_many_columns_rejected(client):
    headers = _auth(client)
    df = pd.DataFrame({f"col_{i}": range(60) for i in range(600)})
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    res = client.post(
        "/api/analysis/upload",
        files={"file": ("wide.csv", buf.getvalue(), "text/csv")},
        headers=headers,
    )
    assert res.status_code == 413


def test_duplicate_columns_rejected(client):
    headers = _auth(client, "uploader2@acme.com", "UploadOrg2")
    raw_csv = "a,a,b\n" + "\n".join(f"{i},{i},{i}" for i in range(60))

    res = client.post(
        "/api/analysis/upload",
        files={"file": ("dupe.csv", raw_csv.encode(), "text/csv")},
        headers=headers,
    )
    assert res.status_code == 400
