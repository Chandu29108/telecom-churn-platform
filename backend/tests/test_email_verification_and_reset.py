"""Email verification + password reset (Phase 1). Tokens are never
returned over the API (they're only emailed), so tests read the raw
token straight out of the test DB via client.db_session_factory — see
conftest.py — the same way a real test-env "email" inbox check would.
"""
from app.models_db import EmailToken


def _latest_token(client, purpose):
    db = client.db_session_factory()
    try:
        record = (
            db.query(EmailToken)
            .filter(EmailToken.purpose == purpose)
            .order_by(EmailToken.id.desc())
            .first()
        )
        return record
    finally:
        db.close()


def test_register_creates_unused_verification_token(client):
    res = client.post("/api/auth/register", json={
        "email": "verify1@acme.com", "password": "testpassword123",
        "full_name": "V", "organization_name": "VerifyOrg",
    })
    assert res.status_code == 201
    record = _latest_token(client, "verify_email")
    assert record is not None
    assert record.used_at is None


def test_verify_email_with_invalid_token_rejected(client):
    res = client.post("/api/auth/verify-email", json={"token": "not-a-real-token"})
    assert res.status_code == 400


def test_me_reflects_verification_state(client, monkeypatch):
    """Round-trips the actual token through the DB (rather than reaching
    for the ORM's own hash function) so this test also proves the
    hash-then-lookup path in routers/auth.py works end to end."""
    import app.routers.auth as auth_router

    # register() generates TWO opaque tokens (the verification token, then
    # the refresh token) — capture them in call order rather than
    # overwriting a single slot, so this test grabs the right one.
    captured = []
    original = auth_router.generate_opaque_token

    def spy():
        raw = original()
        captured.append(raw)
        return raw

    monkeypatch.setattr(auth_router, "generate_opaque_token", spy)

    res = client.post("/api/auth/register", json={
        "email": "verify2@acme.com", "password": "testpassword123",
        "full_name": "V2", "organization_name": "VerifyOrg2",
    })
    verification_raw = captured[0]
    token = res.json()["access_token"]
    me_before = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me_before["is_verified"] is False

    verify_res = client.post("/api/auth/verify-email", json={"token": verification_raw})
    assert verify_res.status_code == 200

    me_after = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me_after["is_verified"] is True

    # One-time use: the same token can't be replayed.
    replay = client.post("/api/auth/verify-email", json={"token": verification_raw})
    assert replay.status_code == 400


def test_resend_verification_gives_generic_response_for_unknown_email(client):
    res = client.post("/api/auth/resend-verification", json={"email": "nobody@nowhere.com"})
    assert res.status_code == 200
    assert "message" in res.json()


def test_forgot_password_gives_generic_response_for_unknown_email(client):
    """Anti-enumeration: response must be identical whether or not the
    account exists (audit report, Part 6, finding #4)."""
    known = client.post("/api/auth/register", json={
        "email": "known@acme.com", "password": "testpassword123",
        "full_name": "K", "organization_name": "KnownOrg",
    })
    assert known.status_code == 201

    known_res = client.post("/api/auth/forgot-password", json={"email": "known@acme.com"})
    unknown_res = client.post("/api/auth/forgot-password", json={"email": "unknown@acme.com"})
    assert known_res.status_code == unknown_res.status_code == 200
    assert known_res.json() == unknown_res.json()


def test_full_password_reset_flow(client, monkeypatch):
    import app.routers.auth as auth_router
    captured = {}
    original = auth_router.generate_opaque_token

    def spy():
        raw = original()
        captured["raw"] = raw
        return raw
    monkeypatch.setattr(auth_router, "generate_opaque_token", spy)

    client.post("/api/auth/register", json={
        "email": "resetme@acme.com", "password": "oldpassword123",
        "full_name": "R", "organization_name": "ResetOrg",
    })
    captured.clear()
    client.post("/api/auth/forgot-password", json={"email": "resetme@acme.com"})
    reset_token = captured["raw"]

    reset_res = client.post("/api/auth/reset-password", json={
        "token": reset_token, "new_password": "brandnewpassword456",
    })
    assert reset_res.status_code == 200

    # Old password no longer works.
    old_login = client.post("/api/auth/login", data={
        "username": "resetme@acme.com", "password": "oldpassword123",
    })
    assert old_login.status_code == 401

    # New password works.
    new_login = client.post("/api/auth/login", data={
        "username": "resetme@acme.com", "password": "brandnewpassword456",
    })
    assert new_login.status_code == 200

    # Token is single-use.
    replay = client.post("/api/auth/reset-password", json={
        "token": reset_token, "new_password": "yetanotherpassword789",
    })
    assert replay.status_code == 400


def test_weak_password_rejected_at_registration(client):
    res = client.post("/api/auth/register", json={
        "email": "weak@acme.com", "password": "password",  # 8 chars but on the common-password blocklist
        "full_name": "W", "organization_name": "WeakOrg",
    })
    assert res.status_code == 400
