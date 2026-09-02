"""
OpenAI-compatible LLM provider — works with any provider that implements
the standard /chat/completions API shape (OpenAI itself, Groq, Together,
Fireworks, OpenRouter, etc.). Which provider you're actually talking to is
entirely determined by OPENAI_BASE_URL + OPENAI_API_KEY in config.py; this
class doesn't know or care which one it is.

Recommended default for production: Groq (https://console.groq.com) — free
tier, fast, and speaks this exact API shape, so no code change is needed
to use it beyond setting the three OPENAI_* env vars. Real OpenAI works
identically if you outgrow Groq's free tier later.
"""
import httpx

from .base import LLMProvider
from ..config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL


class OpenAICompatibleProvider(LLMProvider):
    name = "openai"

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        if not OPENAI_API_KEY:
            # Fails loudly and specifically rather than letting httpx raise
            # a generic 401 from the provider — this is almost always a
            # forgotten env var, and the router should be able to show the
            # user something more useful than a raw HTTP error.
            raise RuntimeError(
                "LLM_PROVIDER is set to 'openai' but OPENAI_API_KEY is not "
                "set. Set OPENAI_API_KEY (and optionally OPENAI_BASE_URL / "
                "OPENAI_MODEL to point at a different OpenAI-compatible "
                "provider, e.g. Groq)."
            )
        response = httpx.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,  # low: this is a data-reporting task, not creative writing
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
