from pathlib import Path

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

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
