from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QUIZZER_", env_file=".env", extra="ignore")

    # Paths
    content_dir: Path = Path("content")
    db_path: Path = Path("data/quizzer.db")

    # Ollama
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
