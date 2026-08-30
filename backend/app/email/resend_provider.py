"""
Resend provider. Picked over AWS SES / SendGrid for this stack specifically
(see the audit report / README for the full reasoning):

- No AWS account/IAM setup needed (this app already avoids AWS elsewhere —
  it uses Cloudflare R2, not S3 — so SES would be the only AWS dependency
  in the whole stack for one feature).
- Simpler API than SendGrid's, and httpx (used here) is already a
  dependency of this project (it's how the Ollama copilot is called), so
  no new package is needed at all.
- Free tier (3,000 emails/month, 100/day) is enough for verification +
  reset emails at this product's current scale; upgrading later is a
  billing change, not a code change.

Only used when EMAIL_PROVIDER=resend and RESEND_API_KEY is set — see
factory.py for the fallback behaviour when it isn't.
"""
import logging

import httpx

from .base import EmailProvider
from ..config import RESEND_API_KEY, EMAIL_FROM_ADDRESS

logger = logging.getLogger("churn_platform.email")

RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailProvider(EmailProvider):
    name = "resend"

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        resp = httpx.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": EMAIL_FROM_ADDRESS,
                "to": [to],
                "subject": subject,
                "html": html,
                "text": text,
            },
            timeout=10.0,
        )
        if resp.status_code >= 400:
            logger.error("email.resend_failed to=%s status=%s body=%s", to, resp.status_code, resp.text)
            raise RuntimeError(f"Resend API error {resp.status_code}")
