"""Adaptive AI client with task-aware model selection and automatic fallback.

How it works
------------
1. The **configured provider** always uses the configured model for generation.
2. For scoring, the configured provider uses `AI_SCORE_MODEL` when set,
   otherwise it uses the same configured model as generation.
3. Fallback providers still use fast/cheap defaults for scoring.
4. If the primary provider call fails, automatically falls back through every
   other provider that has a key/endpoint configured.

Supported providers (set AI_PROVIDER in .env):
  gemini    → Google Gemini API (free tier available)
  openai    → OpenAI ChatGPT models
  anthropic → Anthropic Claude models
  lmstudio  → LM Studio local server (OpenAI-compatible, http://localhost:1234/v1)
  ollama    → Ollama local server (http://localhost:11434)

Fallback priority order:
  gemini → openai → anthropic → lmstudio → ollama

Usage
-----
    from app.core.ai_client import ai_complete

    # Fast scoring call (uses cheaper/faster model)
    result = ai_complete(system, prompt, max_tokens=100, task="score")

    # Full generation call using configured model
    result = ai_complete(system, prompt, max_tokens=2048, task="generate")
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# ── task-specific model overrides ─────────────────────────────────────────────
# Used only for cloud fallback providers when task="score" to keep costs low.
# The configured primary provider always uses the user's chosen model.
_FAST_MODELS: dict[str, str] = {
    "gemini":    "gemini-2.5-flash",
    "openai":    "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    # lmstudio / ollama: no override — use whatever model is loaded locally
}

# Fallback generation models for cloud providers when primary is unavailable
_FALLBACK_GENERATE_MODELS: dict[str, str] = {
    "gemini":    "gemini-2.5-flash",
    "openai":    "gpt-4o",
    "anthropic": "claude-sonnet-4-6",
}

# Provider priority order for fallback chain
_PROVIDER_ORDER = ["gemini", "openai", "anthropic", "lmstudio", "ollama"]


# ── public entry point ────────────────────────────────────────────────────────

def ai_complete(
    system: str,
    prompt: str,
    max_tokens: int = 2048,
    task: str = "generate",          # "score" | "generate" | "general"
) -> str | None:
    """Call the AI with automatic model selection and provider fallback.

    Parameters
    ----------
    system      System / instruction prompt.
    prompt      User prompt.
    max_tokens  Maximum tokens in the response.
    task        "score"    → use a fast, cheap model
                "generate" → use the user-configured model (default)
    """
    settings = get_settings()
    primary   = settings.ai_provider.lower()

    # ── 1. Try configured provider ────────────────────────────────────────────
    model = _pick_model(primary, task, settings)
    logger.debug("AI call: provider=%s model=%s task=%s", primary, model, task)
    result = _call(primary, model, system, prompt, max_tokens, settings)
    if result:
        return result

    logger.warning(
        "Primary AI provider '%s' (model=%s) failed — trying fallbacks. "
        "For LM Studio: ensure the server is running at %s and LMSTUDIO_MODEL "
        "matches the loaded model name exactly.",
        primary, model, settings.lmstudio_base_url,
    )

    # ── 2. Fallback through other available providers ─────────────────────────
    for provider in _PROVIDER_ORDER:
        if provider == primary:
            continue
        if not _has_key(provider, settings):
            continue
        model = _pick_model(provider, task, settings)
        logger.info("Falling back to provider=%s model=%s", provider, model)
        result = _call(provider, model, system, prompt, max_tokens, settings)
        if result:
            return result

    logger.error(
        "All AI providers failed for task=%s — scoring will use heuristics only. "
        "Check that at least one AI provider (LM Studio, Ollama, Gemini, etc.) "
        "is correctly configured in .env or Settings.",
        task,
    )
    return None


def _mask_keys(text: str, settings: Settings) -> str:
    """Replace raw API key values in a string with '[key]' to prevent leaking."""
    for key_val in (
        settings.gemini_api_key,
        settings.openai_api_key,
        settings.anthropic_api_key,
    ):
        if key_val and key_val in text:
            text = text.replace(key_val, "[key]")
    return text


def ai_ping(provider: str | None = None) -> dict:
    """Quick connectivity check.

    Returns {"ok": bool, "provider": str, "model": str, "error": str|None}.

    Unlike ai_complete, this bypasses the _call() wrapper so that real
    connection errors are surfaced instead of silently swallowed.
    """
    settings = get_settings()
    target   = (provider or settings.ai_provider).lower()
    # Use generate task so we get the provider's actual configured model,
    # not an optional score-model override that may point to a cloud provider.
    model    = _pick_model(target, "generate", settings)
    system   = "You are a test assistant."
    prompt   = "Reply with the single word: pong"
    # Local reasoning models (e.g. Gemma thinking variants) need a large token
    # budget to finish their internal thinking before producing a response.
    # Cloud providers use a small budget to keep the ping cheap and fast.
    local_tokens = 1024
    cloud_tokens = 32
    try:
        if target == "lmstudio":
            result = _lmstudio(system, prompt, local_tokens, settings, model)
        elif target == "ollama":
            result = _ollama(system, prompt, local_tokens, settings, model)
        elif target == "gemini":
            result = _gemini(system, prompt, cloud_tokens, settings, model)
        elif target == "openai":
            result = _openai(system, prompt, cloud_tokens, settings, model)
        elif target == "anthropic":
            result = _anthropic(system, prompt, cloud_tokens, settings, model)
        else:
            return {"ok": False, "provider": target, "model": model,
                    "error": f"Unknown provider: {target}"}
        return {"ok": bool(result), "provider": target, "model": model, "error": None}
    except Exception as exc:
        error_msg = _mask_keys(str(exc), settings)
        return {"ok": False, "provider": target, "model": model, "error": error_msg}


# ── internal helpers ──────────────────────────────────────────────────────────

def _has_key(provider: str, settings: Settings) -> bool:
    """Return True if this provider has a key/endpoint configured."""
    if provider == "gemini":    return bool(settings.gemini_api_key)
    if provider == "openai":    return bool(settings.openai_api_key)
    if provider == "anthropic": return bool(settings.anthropic_api_key)
    if provider == "lmstudio":  return bool(settings.lmstudio_base_url)
    if provider == "ollama":    return True   # local, always available
    return False


def _pick_model(provider: str, task: str, settings: Settings) -> str:
    """Select the best model for the given provider and task."""
    if provider == settings.ai_provider.lower():
        if task == "score" and settings.ai_score_model:
            return settings.ai_score_model
        # LM Studio has its own model ID separate from AI_MODEL.
        # AI_MODEL is used by cloud providers; LMSTUDIO_MODEL must match
        # the exact model name shown in LM Studio's "Local Server" tab.
        if provider == "lmstudio" and settings.lmstudio_model and settings.lmstudio_model != "local-model":
            return settings.lmstudio_model
        return settings.ai_model
    # Fallback providers
    if provider == "lmstudio":
        return settings.lmstudio_model
    if provider == "ollama":
        return settings.ai_model
    # Cloud fallback providers
    if task == "score" and provider in _FAST_MODELS:
        return _FAST_MODELS[provider]
    if provider in _FALLBACK_GENERATE_MODELS:
        return _FALLBACK_GENERATE_MODELS[provider]
    return settings.ai_model


def _call(
    provider: str, model: str,
    system: str, prompt: str,
    max_tokens: int, settings: Settings,
) -> str | None:
    """Dispatch to the correct provider implementation."""
    try:
        if provider == "gemini":
            return _gemini(system, prompt, max_tokens, settings, model)
        if provider == "openai":
            return _openai(system, prompt, max_tokens, settings, model)
        if provider == "anthropic":
            return _anthropic(system, prompt, max_tokens, settings, model)
        if provider == "lmstudio":
            return _lmstudio(system, prompt, max_tokens, settings, model)
        if provider == "ollama":
            return _ollama(system, prompt, max_tokens, settings, model)
    except Exception as exc:
        logger.debug("Provider %s/%s raised: %s", provider, model, exc)
    return None


# ── provider implementations ──────────────────────────────────────────────────

def _gemini(
    system: str, prompt: str, max_tokens: int,
    settings: Settings, model: str,
) -> str | None:
    if not settings.gemini_api_key:
        return None
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={settings.gemini_api_key}"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
    }
    response = httpx.post(url, json=payload, timeout=60)

    if response.status_code == 429:
        # Free-tier quota hit — raise a clear, key-free message
        retry_after = response.headers.get("Retry-After", "60")
        raise ValueError(
            f"Gemini rate limit reached (free tier). "
            f"Wait {retry_after}s and try again, or use model 'gemini-1.5-flash' "
            f"which has higher free-tier quotas."
        )
    if response.status_code == 404:
        raise ValueError(
            f"Gemini model '{model}' not found (404). "
            f"Check the model name — try 'gemini-2.0-flash' or 'gemini-1.5-flash'."
        )
    if response.status_code == 400:
        # Often means the model name is wrong
        try:
            detail = response.json().get("error", {}).get("message", "bad request")
        except Exception:
            detail = "bad request"
        raise ValueError(f"Gemini rejected the request (400): {detail}")
    if response.status_code == 403:
        raise ValueError(
            "Gemini API key is invalid or the model requires billing to be enabled. "
            "Check your key in Google AI Studio."
        )

    response.raise_for_status()
    return str(response.json()["candidates"][0]["content"]["parts"][0]["text"])


def _openai(
    system: str, prompt: str, max_tokens: int,
    settings: Settings, model: str,
) -> str | None:
    if not settings.openai_api_key:
        return None
    import openai  # optional dependency
    client = openai.OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
    )
    return response.choices[0].message.content


def _anthropic(
    system: str, prompt: str, max_tokens: int,
    settings: Settings, model: str,
) -> str | None:
    if not settings.anthropic_api_key:
        return None
    import anthropic  # optional dependency
    from anthropic.types import TextBlock
    client  = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    block = response.content[0]
    return block.text if isinstance(block, TextBlock) else None


def _lmstudio(
    system: str, prompt: str, max_tokens: int,
    settings: Settings, model: str,
) -> str | None:
    """LM Studio local server — OpenAI-compatible API.

    Handles reasoning/thinking models (e.g. Gemma, DeepSeek-R1) that spend
    tokens on internal thoughts stored in ``reasoning_content`` before writing
    the actual ``content``.  If the initial request runs out of tokens mid-think
    (content empty, finish_reason "length"), a single retry is made with a
    larger budget so the model can finish reasoning and produce a real response.

    Setup:
      1. Open LM Studio → Local Server tab
      2. Load a model and click "Start Server"
      3. In Settings set: AI_PROVIDER=lmstudio
                          LMSTUDIO_BASE_URL=http://localhost:1234/v1
                          LMSTUDIO_MODEL=<model-id-shown-in-LM-Studio>
    """
    if not settings.lmstudio_base_url:
        return None
    base = settings.lmstudio_base_url.rstrip("/")
    url  = f"{base}/chat/completions"

    def _post(tokens: int) -> dict:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            "max_tokens": tokens,
            "temperature": 0.3,
            "stream": False,
        }
        r = httpx.post(url, json=payload, timeout=180)  # local models can be slow
        r.raise_for_status()
        return r.json()

    data    = _post(max_tokens)
    choice  = data["choices"][0]
    msg     = choice["message"]
    content = msg.get("content") or ""

    # Reasoning model ran out of tokens while thinking → retry with more room
    if (
        not content
        and choice.get("finish_reason") == "length"
        and msg.get("reasoning_content")
    ):
        logger.debug(
            "LM Studio: reasoning model hit token limit (%d), retrying with %d",
            max_tokens, max(max_tokens * 4, 2048),
        )
        data    = _post(max(max_tokens * 4, 2048))
        content = data["choices"][0]["message"].get("content") or ""

    return content if content else None


def _ollama(
    system: str, prompt: str, max_tokens: int,
    settings: Settings, model: str,
) -> str | None:
    response = httpx.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model":   model,
            "stream":  False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            "options": {"num_predict": max_tokens},
        },
        timeout=180,
    )
    response.raise_for_status()
    return str(response.json()["message"]["content"])
