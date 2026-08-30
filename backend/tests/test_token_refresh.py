"""Refresh-token rotation, revocation on logout, reuse detection (audit
report, Part 6, finding #2), and CSRF double-submit protection on the two
endpoints that authenticate purely off the refresh cookie (Phase 1 fix)."""
from app.config import REFRESH_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME


def _csrf_headers(client):
    """Reads the CSRF cookie the client already holds (set by a prior
    register/login/refresh) and returns it as the header a legitimate
    frontend would attach. Mirrors what frontend/src/api.js does with the
    csrf_token value from the JSON response body."""
    token = client.cookies.get(CSRF_COOKIE_NAME)
    return {CSRF_HEADER_NAME: token} if token else {}


def test_register_sets_refresh_cookie(client):
    res = client.post("/api/auth/register", json={
        "email": "refresh1@acme.com", "password": "testpassword123",
        "full_name": "R1", "organization_name": "RefreshOrg1",
    })
    assert res.status_code == 201
    assert REFRESH_COOKIE_NAME in res.cookies
    assert CSRF_COOKIE_NAME in res.cookies
    assert "csrf_token" in res.json()


def test_refresh_without_cookie_rejected(client):
    # No prior login: neither the refresh cookie nor the CSRF cookie
    # exist yet, so this is now rejected by the CSRF check (403) before
    # the route body even runs, rather than the old "no cookie" 401.
    res = client.post("/api/auth/refresh")
    assert res.status_code == 403


def test_refresh_rotates_and_issues_new_access_token(client):
    client.post("/api/auth/register", json={
        "email": "refresh2@acme.com", "password": "testpassword123",
        "full_name": "R2", "organization_name": "RefreshOrg2",
    })
    res = client.post("/api/auth/refresh", headers=_csrf_headers(client))
    assert res.status_code == 200
    assert "access_token" in res.json()
    assert "csrf_token" in res.json()


def test_logout_then_refresh_fails(client):
    client.post("/api/auth/register", json={
        "email": "refresh3@acme.com", "password": "testpassword123",
        "full_name": "R3", "organization_name": "RefreshOrg3",
    })
    logout_res = client.post("/api/auth/logout", headers=_csrf_headers(client))
    assert logout_res.status_code == 200

    # Logout clears the CSRF cookie along with the refresh cookie, so the
    # CSRF check now rejects this before the route body's revoked-token
    # check would even run — 403, not the old 401.
    refresh_res = client.post("/api/auth/refresh", headers=_csrf_headers(client))
    assert refresh_res.status_code == 403


def test_reusing_a_rotated_refresh_token_is_rejected(client):
    """Simulates a stolen-and-replayed refresh cookie: once a token has
    been rotated out, presenting it again must fail, not silently succeed."""
    client.post("/api/auth/register", json={
        "email": "refresh4@acme.com", "password": "testpassword123",
        "full_name": "R4", "organization_name": "RefreshOrg4",
    })
    old_cookie_value = client.cookies.get(REFRESH_COOKIE_NAME)

    first_refresh = client.post("/api/auth/refresh", headers=_csrf_headers(client))
    assert first_refresh.status_code == 200

    # Manually replay the OLD (now-rotated) cookie value. The CSRF cookie
    # is unchanged by this (only the refresh cookie rotates on success in
    # this test's cookie jar until the assertion below), so the existing
    # CSRF header still matches.
    client.cookies.set(REFRESH_COOKIE_NAME, old_cookie_value)
    replay = client.post("/api/auth/refresh", headers=_csrf_headers(client))
    assert replay.status_code == 401


def test_refresh_without_csrf_header_is_rejected(client):
    """The core Phase 1 regression test: a valid refresh cookie alone is
    no longer enough — this is exactly the cross-site-request scenario
    CSRF protection defends against (browser auto-attaches the cookie,
    attacker page can't supply the header)."""
    client.post("/api/auth/register", json={
        "email": "refresh5@acme.com", "password": "testpassword123",
        "full_name": "R5", "organization_name": "RefreshOrg5",
    })
    res = client.post("/api/auth/refresh")  # no X-CSRF-Token header
    assert res.status_code == 403


def test_refresh_with_wrong_csrf_header_is_rejected(client):
    client.post("/api/auth/register", json={
        "email": "refresh6@acme.com", "password": "testpassword123",
        "full_name": "R6", "organization_name": "RefreshOrg6",
    })
    res = client.post("/api/auth/refresh", headers={CSRF_HEADER_NAME: "not-the-real-token"})
    assert res.status_code == 403


def test_logout_without_csrf_header_is_rejected(client):
    client.post("/api/auth/register", json={
        "email": "refresh7@acme.com", "password": "testpassword123",
        "full_name": "R7", "organization_name": "RefreshOrg7",
    })
    res = client.post("/api/auth/logout")  # no X-CSRF-Token header
    assert res.status_code == 403
