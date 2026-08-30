"""
Config-driven provider selection (same pattern as app/llm/factory.py) plus
the two templated emails this product currently sends. Templates are kept
minimal HTML + a plain-text fallback — no external template engine needed
for two emails.
"""
import logging

from ..config import EMAIL_PROVIDER, FRONTEND_URL
from .base import EmailProvider
from .console_provider import ConsoleEmailProvider

logger = logging.getLogger("churn_platform.email")


def get_email_provider() -> EmailProvider:
    if EMAIL_PROVIDER == "resend":
        from .resend_provider import ResendEmailProvider
        return ResendEmailProvider()
    return ConsoleEmailProvider()


def send_verification_email(to: str, token: str) -> None:
    link = f"{FRONTEND_URL}/verify-email?token={token}"
    provider = get_email_provider()
    try:
        provider.send(
            to=to,
            subject="Verify your email — Telecom Churn Intelligence Platform",
            html=(
                f"<p>Confirm your email address to finish setting up your account.</p>"
                f'<p><a href="{link}">Verify my email</a></p>'
                f"<p>This link expires in 24 hours. If you didn't create this account, you can ignore this email.</p>"
            ),
            text=f"Verify your email: {link}\n\nThis link expires in 24 hours.",
        )
    except Exception:
        # Never let a downstream email failure fail the account action that
        # triggered it (registration/resend already succeeded) — log and
        # move on, matching the SHAP-explainability failure pattern already
        # used in routers/analysis.py.
        logger.exception("email.verification_send_failed to=%s", to)


def send_password_reset_email(to: str, token: str) -> None:
    link = f"{FRONTEND_URL}/reset-password?token={token}"
    provider = get_email_provider()
    try:
        provider.send(
            to=to,
            subject="Reset your password — Telecom Churn Intelligence Platform",
            html=(
                f"<p>We received a request to reset your password.</p>"
                f'<p><a href="{link}">Reset my password</a></p>'
                f"<p>This link expires in 30 minutes and can only be used once. "
                f"If you didn't request this, you can safely ignore this email — "
                f"your password won't change."
            ),
            text=f"Reset your password: {link}\n\nThis link expires in 30 minutes and can only be used once.",
        )
    except Exception:
        logger.exception("email.reset_send_failed to=%s", to)
