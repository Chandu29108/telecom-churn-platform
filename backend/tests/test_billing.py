"""Billing (Lemon Squeezy) tests.

Covers the three things that would actually be dangerous to get wrong:
  - a non-owner triggering checkout (billing actions should be owner-only,
    same gate as invites/model rollback)
  - a webhook request with a missing/wrong signature (must be rejected —
    otherwise anyone could POST a fake "subscription active" event and
    upgrade their own org for free)
  - the webhook correctly flipping org.plan based on subscription status

Doesn't hit the real Lemon Squeezy API — /checkout is only exercised via
its config-gate and auth-gate (a real call needs live API creds this
suite deliberately never has, matching the pattern for LLM_PROVIDER/R2
elsewhere: unconfigured in test/dev is expected, not an error).
"""
import hashlib
import hmac

from app.config import LEMON_SQUEEZY_WEBHOOK_SECRET
from app.models_db import Organization


def _register(client, email, org):
    res = client.post("/api/auth/register", json={
        "email": email, "password": "testpassword123",
        "full_name": "T", "organization_name": org,
    })
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_new_org_defaults_to_free_plan(client):
    headers = _register(client, "owner@billingorg.com", "Billing Org")
    res = client.get("/api/billing/status", headers=headers)
    assert res.status_code == 200
    assert res.json() == {"plan": "free", "subscription_status": None}


def test_member_cannot_create_checkout(client):
    """Same require_owner gate as invites/model rollback — billing is an
    org-management action, not something every member should trigger."""
    owner_headers = _register(client, "owner@checkoutorg.com", "Checkout Org")
    invite_token = client.post("/api/auth/invites", json={}, headers=owner_headers).json()["token"]

    member_res = client.post("/api/auth/register", json={
        "email": "member@checkoutorg.com", "password": "testpassword123",
        "full_name": "Member", "organization_name": "Checkout Org", "invite_token": invite_token,
    })
    member_headers = {"Authorization": f"Bearer {member_res.json()['access_token']}"}

    res = client.post("/api/billing/checkout", headers=member_headers)
    # 403 (not owner) must win over 503 (not configured) — a member should
    # never learn whether billing is configured on this deployment.
    assert res.status_code == 403


def test_owner_checkout_without_config_returns_503(client):
    """No LEMON_SQUEEZY_* env vars are set in the test environment — this
    should fail with a clear, deliberate 503, not a confusing crash trying
    to call the real API with empty credentials."""
    owner_headers = _register(client, "owner@unconfiguredorg.com", "Unconfigured Org")
    res = client.post("/api/billing/checkout", headers=owner_headers)
    assert res.status_code == 503


def test_webhook_rejects_missing_signature(client):
    res = client.post("/api/billing/webhook", json={"meta": {"event_name": "subscription_created"}})
    assert res.status_code == 401


def test_webhook_rejects_wrong_signature(client):
    body = b'{"meta": {"event_name": "subscription_created"}}'
    res = client.post(
        "/api/billing/webhook",
        content=body,
        headers={"X-Signature": "not-the-real-signature", "Content-Type": "application/json"},
    )
    assert res.status_code == 401


def test_webhook_with_valid_signature_upgrades_org_to_pro(client, monkeypatch):
    """The core webhook behavior: a correctly-signed subscription_created
    event with status=active should flip the target org's plan to pro."""
    monkeypatch.setattr("app.routers.billing.LEMON_SQUEEZY_WEBHOOK_SECRET", "test-webhook-secret")

    owner_headers = _register(client, "owner@webhookorg.com", "Webhook Org")
    me = client.get("/api/auth/me", headers=owner_headers).json()
    org_id = me["org_id"]

    payload = {
        "meta": {
            "event_name": "subscription_created",
            "custom_data": {"org_id": str(org_id)},
        },
        "data": {
            "id": "12345",
            "attributes": {"status": "active", "customer_id": 999},
        },
    }
    import json
    body = json.dumps(payload).encode()
    signature = _sign(body, "test-webhook-secret")

    res = client.post(
        "/api/billing/webhook",
        content=body,
        headers={"X-Signature": signature, "Content-Type": "application/json"},
    )
    assert res.status_code == 200

    status_res = client.get("/api/billing/status", headers=owner_headers)
    assert status_res.json() == {"plan": "pro", "subscription_status": "active"}


def test_webhook_cancelled_subscription_reverts_org_to_free(client, monkeypatch):
    """The other direction — a cancelled/expired event must revert plan to
    free, not just leave it stuck on pro from a prior active event."""
    monkeypatch.setattr("app.routers.billing.LEMON_SQUEEZY_WEBHOOK_SECRET", "test-webhook-secret")

    owner_headers = _register(client, "owner@cancelorg.com", "Cancel Org")
    me = client.get("/api/auth/me", headers=owner_headers).json()
    org_id = me["org_id"]

    import json

    def send(status_value):
        payload = {
            "meta": {"event_name": "subscription_updated", "custom_data": {"org_id": str(org_id)}},
            "data": {"id": "12345", "attributes": {"status": status_value, "customer_id": 999}},
        }
        body = json.dumps(payload).encode()
        signature = _sign(body, "test-webhook-secret")
        return client.post(
            "/api/billing/webhook", content=body,
            headers={"X-Signature": signature, "Content-Type": "application/json"},
        )

    assert send("active").status_code == 200
    assert client.get("/api/billing/status", headers=owner_headers).json()["plan"] == "pro"

    assert send("cancelled").status_code == 200
    assert client.get("/api/billing/status", headers=owner_headers).json()["plan"] == "free"


def test_webhook_ignores_events_without_org_id(client, monkeypatch):
    """Not every Lemon Squeezy event carries our custom_data (e.g.
    order_created) — these should be acknowledged, not errored."""
    monkeypatch.setattr("app.routers.billing.LEMON_SQUEEZY_WEBHOOK_SECRET", "test-webhook-secret")

    import json
    payload = {"meta": {"event_name": "order_created"}, "data": {}}
    body = json.dumps(payload).encode()
    signature = _sign(body, "test-webhook-secret")

    res = client.post(
        "/api/billing/webhook", content=body,
        headers={"X-Signature": signature, "Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json() == {"status": "ignored"}
