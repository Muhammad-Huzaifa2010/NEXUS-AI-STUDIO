from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "NEXUS AI STUDIO"
    app_version: str = "1.0.0"
    debug: bool = False
    frontend_url: str = "http://localhost:5173"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    tavily_api_key: str = ""
    database_url: str = ""
    citation_validation_retries: int = Field(default=1, ge=0, le=3)
    research_search_budget: int = Field(default=5, ge=1, le=8)
    research_results_per_query: int = Field(default=5, ge=1, le=10)
    research_max_sources: int = Field(default=6, ge=1, le=10)

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
