"""
Abstract provider interface so the copilot router never talks to a
specific vendor SDK directly. Same pattern as the pluggable LLM provider
in the AI Financial Research Assistant project — swapping LLM_PROVIDER in
.env is the only change needed to move from a free local model to a paid
API later; no router code changes.
"""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Return the model's reply as plain text. Implementations should
        raise on failure (timeout, connection refused, bad response) rather
        than silently returning an empty string, so the router can surface
        a clear, actionable error to the user."""
        raise NotImplementedError
