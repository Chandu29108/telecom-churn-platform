"""
Default provider: logs the email instead of sending it. This is what
EMAIL_PROVIDER=console (the default — see app/config.py) uses, so
registration/password-reset flows work end-to-end in local dev and CI with
zero external credentials. The verification/reset link is logged in full,
so a developer can copy it straight out of the terminal to test the flow
manually.
"""
import logging

from .base import EmailProvider

logger = logging.getLogger("churn_platform.email")


class ConsoleEmailProvider(EmailProvider):
    name = "console"

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        logger.info(
            "email.console_send to=%s subject=%r\n----- text body -----\n%s\n----------------------",
            to, subject, text,
        )
