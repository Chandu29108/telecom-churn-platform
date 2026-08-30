"""
Email provider abstraction — mirrors the existing pattern in this codebase
(see app/llm/base.py + factory.py, app/model_store.py): a small interface,
config-driven selection, and a safe no-op default so local dev/CI never
need real credentials.
"""
from abc import ABC, abstractmethod


class EmailProvider(ABC):
    name: str = "base"

    @abstractmethod
    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        """Send an email. Raise on failure — callers decide how to handle
        that (see routers/auth.py, which never lets an email failure block
        the underlying account action, only logs it)."""
        raise NotImplementedError
