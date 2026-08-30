"""
Single switch point for which LLM backs the copilot. To add a paid
provider later: implement LLMProvider in a new module (e.g.
openai_provider.py), add one `elif` branch here, set LLM_PROVIDER=openai
in .env. Nothing in routers/copilot.py needs to change.
"""
from ..config import LLM_PROVIDER
from .base import LLMProvider
from .ollama_provider import OllamaProvider


def get_llm_provider() -> LLMProvider:
    if LLM_PROVIDER == "ollama":
        return OllamaProvider()
    raise ValueError(
        f"Unsupported LLM_PROVIDER '{LLM_PROVIDER}'. Only 'ollama' is wired up today — "
        f"add a provider module in app/llm/ and a branch here to support others."
    )
