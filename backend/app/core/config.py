from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "job-seeking-mate-api"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://jobmate:jobmate@localhost:5432/jobmate"
    redis_url: str = "redis://localhost:6379/0"

    cors_origins: list[str] = ["http://localhost:5173"]

    # AI provider — set ai_provider to "ollama", "openai", or "anthropic"
    ai_provider: str = "ollama"
    ai_model: str = "llama3.2"
    ollama_base_url: str = "http://localhost:11434"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Local dev — path to a PDF resume to auto-ingest on first startup
    default_resume_pdf: str = ""

    # Job search providers
    adzuna_app_id: str = ""
    adzuna_api_key: str = ""
    adzuna_country: str = "au"  # au | us | gb | ca | de | fr | in | nz | sg
    jsearch_api_key: str = ""  # RapidAPI key — aggregates Indeed, LinkedIn, Glassdoor

    # Application settings
    auto_apply_threshold: int = 75
    max_jobs_per_search: int = 50
    match_reject_threshold: int = 60

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
