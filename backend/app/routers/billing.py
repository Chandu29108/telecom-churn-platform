"""
Lemon Squeezy billing integration.

Three endpoints:
  - POST /api/billing/checkout — owner-only, creates a Lemon Squeezy
    Checkout and returns its URL for the frontend to redirect to.
  - GET  /api/billing/status   — any org member can see the org's current
    plan (read-only, not sensitive — matches how upload caps etc. are
    already visible to every member).
  - POST /api/billing/webhook  — public (Lemon Squeezy can't send our
    auth headers), verified instead via HMAC signature over the raw
    request body. This is what actually flips org.plan to "pro" — the
    checkout redirect alone proves nothing; only a signed webhook does.

Chose Lemon Squeezy over Stripe specifically because Stripe is currently
invite-only for India-based accounts, and Lemon Squeezy's Merchant-of-
Record model means we don't have to handle international sales tax/VAT/
GST ourselves.
"""
import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import (
    FRONTEND_URL,
    LEMON_SQUEEZY_API_KEY,
    LEMON_SQUEEZY_PRO_VARIANT_ID,
    LEMON_SQUEEZY_STORE_ID,
    LEMON_SQUEEZY_WEBHOOK_SECRET,
)
from ..database import get_db
from ..deps import get_current_user, require_owner
from ..models_db import Organization, User
from ..schemas import BillingStatusOut, CheckoutOut

logger = logging.getLogger("churn_platform.billing")
router = APIRouter(prefix="/api/billing", tags=["billing"])

LEMON_SQUEEZY_API_BASE = "https://api.lemonsqueezy.com/v1"


def _require_configured() -> None:
    """All four env vars are required for real checkout/webhook traffic;
    unset in local dev is fine (mirrors the LLM/R2 config pattern) — this
    just turns a confusing downstream failure into a clear one."""
    if not all([
        LEMON_SQUEEZY_API_KEY, LEMON_SQUEEZY_STORE_ID,
        LEMON_SQUEEZY_PRO_VARIANT_ID, LEMON_SQUEEZY_WEBHOOK_SECRET,
    ]):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Billing isn't configured on this deployment yet.",
        )


@router.get("/status", response_model=BillingStatusOut)
def billing_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org = db.get(Organization, current_user.org_id)
    return BillingStatusOut(plan=org.plan, subscription_status=org.subscription_status)


@router.post("/checkout", response_model=CheckoutOut)
def create_checkout(
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Creates a Lemon Squeezy Checkout scoped to the caller's org and
    returns its hosted URL. org_id is threaded through as custom_data so
    the webhook (which has no session/auth context of its own) knows
    which org to upgrade once payment succeeds."""
    _require_configured()
    org = db.get(Organization, current_user.org_id)

    resp = httpx.post(
        f"{LEMON_SQUEEZY_API_BASE}/checkouts",
        headers={
            "Authorization": f"Bearer {LEMON_SQUEEZY_API_KEY}",
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json",
        },
        json={
            "data": {
                "type": "checkouts",
                "attributes": {
                    "checkout_data": {
                        "email": current_user.email,
                        "custom": {"org_id": str(org.id)},
                    },
                    "product_options": {
                        "redirect_url": f"{FRONTEND_URL}/team?upgraded=true",
                    },
                },
                "relationships": {
                    "store": {"data": {"type": "stores", "id": str(LEMON_SQUEEZY_STORE_ID)}},
                    "variant": {"data": {"type": "variants", "id": str(LEMON_SQUEEZY_PRO_VARIANT_ID)}},
                },
            }
        },
        timeout=15,
    )
    if resp.status_code >= 400:
        logger.warning(
            "billing.checkout_create_failed status=%s body=%s", resp.status_code, resp.text
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not start checkout — try again shortly.")

    checkout_url = resp.json()["data"]["attributes"]["url"]
    return CheckoutOut(checkout_url=checkout_url)


def _verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """HMAC-SHA256 over the raw request body, keyed with the webhook
    secret set in Lemon Squeezy's dashboard (Settings > Webhooks). Uses
    hmac.compare_digest specifically to avoid a timing side-channel that
    a naive `==` string comparison would have."""
    if not signature_header or not LEMON_SQUEEZY_WEBHOOK_SECRET:
        return False
    expected = hmac.new(
        LEMON_SQUEEZY_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# Every event that means "this org's subscription is currently good" maps
# to plan=pro; everything else (cancelled, expired, unpaid, past_due) maps
# back to free. Listed explicitly rather than inverted, so a new/unknown
# status Lemon Squeezy might introduce later fails safe (org stays/reverts
# to free) instead of silently granting Pro access.
_ACTIVE_STATUSES = {"active", "on_trial"}


@router.post("/webhook")
async def lemon_squeezy_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("X-Signature", "")

    if not _verify_signature(raw_body, signature):
        logger.warning("billing.webhook_bad_signature")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature.")

    payload = await request.json()
    event_name = payload.get("meta", {}).get("event_name", "")
    custom_data = payload.get("meta", {}).get("custom_data", {}) or {}
    org_id = custom_data.get("org_id")

    if not org_id:
        # Not every Lemon Squeezy event is subscription-related (e.g.
        # order_created) or carries our custom_data — acknowledge with 200
        # so Lemon Squeezy doesn't retry something we deliberately ignore,
        # rather than erroring on events outside this webhook's scope.
        logger.info("billing.webhook_ignored event=%s (no org_id)", event_name)
        return {"status": "ignored"}

    org = db.get(Organization, int(org_id))
    if org is None:
        logger.warning("billing.webhook_unknown_org org_id=%s event=%s", org_id, event_name)
        return {"status": "ignored"}

    if event_name.startswith("subscription_"):
        attrs = payload.get("data", {}).get("attributes", {})
        sub_status = attrs.get("status", "")
        org.subscription_status = sub_status
        org.lemon_squeezy_customer_id = str(attrs.get("customer_id", "")) or org.lemon_squeezy_customer_id
        org.lemon_squeezy_subscription_id = str(payload.get("data", {}).get("id", "")) or org.lemon_squeezy_subscription_id
        org.plan = "pro" if sub_status in _ACTIVE_STATUSES else "free"
        db.commit()
        logger.info(
            "billing.subscription_updated org_id=%s event=%s status=%s plan=%s",
            org.id, event_name, sub_status, org.plan,
        )

    return {"status": "ok"}
