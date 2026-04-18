"""Runtime settings — read current AI config and test connectivity.

GET  /settings        → return current AI provider config (keys masked)
POST /settings        → persist AI provider overrides to data/user_settings.json
                        and reload the settings cache
POST /settings/ping   → quick connectivity test for the active (or specified) provider
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.ai_client import ai_ping
from app.core.config import apply_user_overrides, get_settings
from app.core.security import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()

_SETTINGS_FILE = Path("data/user_settings.json")


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_overrides() -> dict:
    try:
        if _SETTINGS_FILE.exists():
            return json.loads(_SETTINGS_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_overrides(data: dict) -> None:
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(data, indent=2))


# ── schemas ───────────────────────────────────────────────────────────────────

class AISettingsUpdate(BaseModel):
    ai_provider:        str | None = None
    ai_model:           str | None = None
    ai_score_model:     str | None = None
    lmstudio_base_url:  str | None = None
    lmstudio_model:     str | None = None
    ollama_base_url:    str | None = None
    auto_apply_threshold:    int | None = None
    match_reject_threshold:  int | None = None


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/settings")
def get_settings_view(_: str = Depends(require_auth)):
    """Return current runtime settings (API keys shown only as present/absent)."""
    s = get_settings()
    overrides = _load_overrides()
    return {
        "ai_provider":       overrides.get("ai_provider",       s.ai_provider),
        "ai_model":          overrides.get("ai_model",          s.ai_model),
        "ai_score_model":    overrides.get("ai_score_model",    s.ai_score_model),
        "lmstudio_base_url": overrides.get("lmstudio_base_url", s.lmstudio_base_url),
        "lmstudio_model":    overrides.get("lmstudio_model",    s.lmstudio_model),
        "ollama_base_url":   overrides.get("ollama_base_url",   s.ollama_base_url),
        "auto_apply_threshold":   overrides.get("auto_apply_threshold",   s.auto_apply_threshold),
        "match_reject_threshold": overrides.get("match_reject_threshold", s.match_reject_threshold),
        # API key presence (never expose the actual keys)
        "has_anthropic": bool(s.anthropic_api_key),
        "has_openai":    bool(s.openai_api_key),
        "has_gemini":    bool(s.gemini_api_key),
        "providers_available": _available_providers(s),
    }


@router.post("/settings")
def update_settings(body: AISettingsUpdate, _: str = Depends(require_auth)):
    """Persist AI provider overrides.

    Only non-None fields are written. Changes take effect immediately:
    env vars are updated first, then the settings cache is refreshed so
    the very next AI call uses the new configuration.
    """
    overrides = _load_overrides()
    updates = body.model_dump(exclude_none=True)
    overrides.update(updates)
    _save_overrides(overrides)

    # Apply to os.environ FIRST, then clear the cache so the next
    # get_settings() call builds a fresh Settings instance from the new vars.
    apply_user_overrides()
    get_settings.cache_clear()

    return {"ok": True, "saved": list(updates.keys())}


@router.post("/settings/ping")
def ping_provider(provider: str | None = None, _: str = Depends(require_auth)):
    """Test connectivity to the specified (or currently configured) AI provider.

    Always returns HTTP 200. The ``ok`` field in the body signals success or
    failure so the frontend can display the actual error message rather than
    receiving an opaque 503 exception.
    """
    return ai_ping(provider)


@router.delete("/settings")
def reset_settings(_: str = Depends(require_auth)):
    """Remove all user overrides and revert to .env / defaults."""
    if _SETTINGS_FILE.exists():
        _SETTINGS_FILE.unlink()
    get_settings.cache_clear()
    return {"ok": True, "message": "Settings reset to environment defaults"}


# ── private helpers ───────────────────────────────────────────────────────────

def _available_providers(s) -> list[str]:
    available = []
    if s.gemini_api_key:    available.append("gemini")
    if s.openai_api_key:    available.append("openai")
    if s.anthropic_api_key: available.append("anthropic")
    available.append("lmstudio")   # local — always listed
    available.append("ollama")     # local — always listed
    return available
