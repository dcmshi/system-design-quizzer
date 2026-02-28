from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QUIZZER_", env_file=".env", extra="ignore")

    # Paths
    content_dir: Path = Path("content")
    db_path: Path = Path("data/quizzer.db")

    # LLM provider: 'auto' | 'gemini' | 'ollama'
    llm_provider: str = "auto"

    # Google AI Studio (Gemini)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    # Ollama (local fallback)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_temperature: float = 0.1
    ollama_seed: int = 42

    # Chunking
    chunk_word_min: int = 300
    chunk_word_max: int = 800

    # Validation
    min_explanation_length: int = 50


settings = Settings()
