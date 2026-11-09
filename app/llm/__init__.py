from __future__ import annotations

from app.core.config import get_config
from app.llm.base import LLMError, LLMProvider, LLMResponse  # noqa: F401


def get_provider(name: str | None = None) -> LLMProvider:
    """Provider is chosen by config/env (LLM_PROVIDER). OpenAI is intentionally not supported."""
    name = (name or get_config()["llm"]["provider"]).lower()
    if name == "mock":
        from app.llm.mock import MockProvider
        return MockProvider()
    if name == "ollama":
        from app.llm.ollama import OllamaProvider
        return OllamaProvider()
    raise ValueError(f"Unknown LLM provider '{name}' (use 'ollama' or 'mock')")
