def test_unhandled_exception_returns_safe_generic_response(client, monkeypatch):
    """An uncaught exception anywhere in a route must never leak a stack
    trace, file paths, or internal details to the client — just a generic
    message plus a request ID for support/log correlation."""
    import app.routers.auth as auth_router

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated internal failure: /app/app/routers/auth.py secret detail")

    monkeypatch.setattr(auth_router, "hash_password", _boom)

    res = client.post("/api/auth/register", json={
        "email": "willfail@example.com", "password": "testpassword123",
        "full_name": "Will Fail", "organization_name": "Failing Org",
    })

    assert res.status_code == 500
    body = res.json()
    assert body["detail"] == (
        "An unexpected error occurred. Please try again, and contact "
        "support with this request ID if it persists."
    )
    assert "request_id" in body
    # Nothing from the real exception message (paths, internals) should
    # ever reach the client.
    assert "secret detail" not in res.text
    assert "routers/auth.py" not in res.text
    assert "Traceback" not in res.text


def test_response_includes_request_id_header(client):
    res = client.get("/api/health")
    assert "X-Request-ID" in res.headers


def test_response_includes_baseline_security_headers(client):
    """These should be present regardless of environment."""
    res = client.get("/api/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_hsts_and_csp_only_sent_in_production(client, monkeypatch):
    """HSTS/CSP are meaningless (HSTS) or would break /docs (CSP) outside
    production, so they're conditional on ENVIRONMENT — verify both the
    "on" and "off" cases rather than just one, so a future refactor that
    accidentally always/never sends them gets caught either direction."""
    import app.main as main_module

    monkeypatch.setattr(main_module, "ENVIRONMENT", "test")
    res_non_prod = client.get("/api/health")
    assert "Strict-Transport-Security" not in res_non_prod.headers
    assert "Content-Security-Policy" not in res_non_prod.headers

    monkeypatch.setattr(main_module, "ENVIRONMENT", "production")
    res_prod = client.get("/api/health")
    assert res_prod.headers["Strict-Transport-Security"] == "max-age=63072000; includeSubDomains"
    assert res_prod.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
