from quizzer.config import settings
from quizzer.generation.base import LLMClient
from quizzer.generation.gemini_client import GeminiClient
from quizzer.generation.ollama_client import OllamaClient


def create_llm_client(
    provider: str | None = None,
    model: str | None = None,
) -> LLMClient:
    """Return an LLM client for the requested provider.

    provider values:
      'gemini'  — Google AI Studio (requires QUIZZER_GEMINI_API_KEY)
      'ollama'  — local Ollama instance
      'auto'    — Gemini if API key is set, else Ollama (default)
    """
    p = provider or settings.llm_provider

    if p == "gemini":
        if not settings.gemini_api_key:
            raise ValueError(
                "QUIZZER_GEMINI_API_KEY must be set when llm_provider=gemini"
            )
        return GeminiClient(
            api_key=settings.gemini_api_key,
            model=model or settings.gemini_model,
        )

    if p == "ollama":
        return OllamaClient(model=model or settings.ollama_model)

    # auto: prefer Gemini when an API key is available
    if settings.gemini_api_key:
        return GeminiClient(
            api_key=settings.gemini_api_key,
            model=model or settings.gemini_model,
        )
    return OllamaClient(model=model or settings.ollama_model)
