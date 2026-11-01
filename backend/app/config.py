from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "PaperPilot PDF Assistant"
    environment: str = "development"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://ai:ai@localhost:5532/ai"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    default_pdf_url: str = "https://phi-public.s3.amazonaws.com/recipes/ThaiRecipes.pdf"
    document_collection: str = "pdf_assistant_documents"
    assistant_table: str = "pdf_assistant"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()
