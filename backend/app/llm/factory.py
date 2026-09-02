"""
Single switch point for which LLM backs the copilot. To add a paid
provider later: implement LLMProvider in a new module (e.g.
openai_provider.py), add one `elif` branch here, set LLM_PROVIDER=openai
in .env. Nothing in routers/copilot.py needs to change.
"""
from ..config import LLM_PROVIDER
from .base import LLMProvider
from .ollama_provider import OllamaProvider
from .openai_compatible_provider import OpenAICompatibleProvider


def get_llm_provider() -> LLMProvider:
    if LLM_PROVIDER == "ollama":
        return OllamaProvider()
    if LLM_PROVIDER == "openai":
        return OpenAICompatibleProvider()
    raise ValueError(
        f"Unsupported LLM_PROVIDER '{LLM_PROVIDER}'. Supported values are "
        f"'ollama' (local, free, dev default) and 'openai' (OpenAI-"
        f"compatible — OpenAI itself, or Groq/Together/etc. via "
        f"OPENAI_BASE_URL). Add a provider module in app/llm/ and a "
        f"branch here to support others."
    )
