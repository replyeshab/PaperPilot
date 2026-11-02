"""Application configuration, loaded from environment variables (and backend/.env locally)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "PaperPilot"
    environment: str = "development"

    # PostgreSQL with pgvector. Use the direct (non-pooled) Neon connection string with sslmode=require.
    database_url: str = "postgresql+psycopg://ai:ai@localhost:5532/ai"

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Embeddings: "auto" uses OpenAI when OPENAI_API_KEY is set, otherwise local FastEmbed.
    # Pick one and keep it: vectors from different embedders cannot be searched together.
    embedder: str = "auto"
    openai_api_key: str = ""
    embedding_model: str = ""

    default_pdf_url: str = "https://phi-public.s3.amazonaws.com/recipes/ThaiRecipes.pdf"
    document_collection: str = "pdf_assistant_documents"
    assistant_table: str = "pdf_assistant"

    # Shared, lifetime budget for paid calls (questions and document additions), across all users.
    request_limit: int = 25

    session_ttl_days: int = 30
    login_max_failures: int = 10
    login_window_seconds: int = 900

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Keep uploads bounded for the free-tier API process. Override with
    # MAX_UPLOAD_MB in production if the deployment has more memory available.
    max_upload_mb: int = 50

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
