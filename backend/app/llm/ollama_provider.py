"""
Default LLM provider: a local Ollama server. No API key, no per-token
cost, works fully offline once the model is pulled — deliberately the
default so the copilot feature never gates a demo or an interview walk-
through behind someone else's billing.

Requires Ollama running locally (`ollama serve`, default port 11434) and
the configured model pulled (`ollama pull llama3.1`, or set OLLAMA_MODEL
to a smaller model like `llama3.2:1b` for lower-spec machines).
"""
import httpx

from .base import LLMProvider
from ..config import OLLAMA_BASE_URL, OLLAMA_MODEL


class OllamaProvider(LLMProvider):
    name = "ollama"

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.2},  # low temperature: this is a data-reporting task, not creative writing
            },
            timeout=90.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]
