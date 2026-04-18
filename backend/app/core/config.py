import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# ── override persistence ───────────────────────────────────────────────────────

_OVERRIDE_FILE = Path("data/user_settings.json")

# Maps JSON key → environment variable name (pydantic-settings reads these)
OVERRIDE_ENV_MAP: dict[str, str] = {
    "ai_provider":            "AI_PROVIDER",
    "ai_model":               "AI_MODEL",
    "ai_score_model":         "AI_SCORE_MODEL",
    "lmstudio_base_url":      "LMSTUDIO_BASE_URL",
    "lmstudio_model":         "LMSTUDIO_MODEL",
    "ollama_base_url":        "OLLAMA_BASE_URL",
    "auto_apply_threshold":   "AUTO_APPLY_THRESHOLD",
    "match_reject_threshold": "MATCH_REJECT_THRESHOLD",
}


def apply_user_overrides() -> None:
    """Read data/user_settings.json and set env vars so get_settings() picks them up.

    Must be called before get_settings() — including at startup — so that
    user-saved settings survive server restarts.
    """
    if not _OVERRIDE_FILE.exists():
        return
    try:
        overrides = json.loads(_OVERRIDE_FILE.read_text())
    except Exception:
        return
    for key, env_var in OVERRIDE_ENV_MAP.items():
        if key in overrides:
            os.environ[env_var] = str(overrides[key])


# ── settings model ─────────────────────────────────────────────────────────────

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True)

    app_env: str = "development"
    app_name: str = "job-seeking-mate-api"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://jobmate:jobmate@localhost:5432/jobmate"
    redis_url: str = "redis://localhost:6379/0"

    cors_origins: str = "http://localhost:5173"

    # AI provider — "gemini" | "openai" | "anthropic" | "lmstudio" | "ollama"
    ai_provider: str = "gemini"
    ai_model: str = "gemini-2.5-flash"
    ai_score_model: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""

    # Ollama (local)
    ollama_base_url: str = "http://localhost:11434"

    # LM Studio — OpenAI-compatible local server (https://lmstudio.ai)
    # Start LM Studio → Local Server → Start Server, then set AI_PROVIDER=lmstudio
    lmstudio_base_url: str = "http://localhost:1234/v1"
    lmstudio_model: str = "local-model"  # must match the model loaded in LM Studio

    # Local dev — path to a PDF resume to auto-ingest on first startup
    default_resume_pdf: str = ""

    # Job search providers
    adzuna_app_id: str = ""
    adzuna_api_key: str = ""
    adzuna_country: str = "au"  # au | us | gb | ca | de | fr | in | nz | sg
    jsearch_api_key: str = ""  # RapidAPI key — aggregates Indeed, LinkedIn, Glassdoor

    # Auth
    jwt_secret_key: str = "change-me-in-production"
    app_username: str = "admin"
    app_password: str = "jobmate"

    # Application settings
    auto_apply_threshold: int = 75
    max_jobs_per_search: int = 50
    match_reject_threshold: int = 60


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
