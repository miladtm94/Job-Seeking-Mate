import logging

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def ai_complete(system: str, prompt: str, max_tokens: int = 2048) -> str | None:
    settings = get_settings()
    provider = settings.ai_provider.lower()

    if provider == "ollama":
        return _ollama_complete(system, prompt, settings)
    if provider == "openai":
        return _openai_complete(system, prompt, max_tokens, settings)
    if provider == "anthropic":
        return _anthropic_complete(system, prompt, max_tokens, settings)

    logger.warning("Unknown ai_provider '%s' — AI features disabled", provider)
    return None


def _ollama_complete(system: str, prompt: str, settings: Settings) -> str | None:
    try:
        response = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ai_model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=120,
        )
        response.raise_for_status()
        return str(response.json()["message"]["content"])
    except Exception:
        logger.exception("Ollama request failed — falling back to heuristics")
        return None


def _openai_complete(system: str, prompt: str, max_tokens: int, settings: Settings) -> str | None:
    try:
        import openai  # optional dependency
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY not set")
            return None
        client = openai.OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.ai_model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
    except Exception:
        logger.exception("OpenAI request failed")
        return None


def _anthropic_complete(
    system: str, prompt: str, max_tokens: int, settings: Settings
) -> str | None:
    try:
        import anthropic  # optional dependency
        from anthropic.types import TextBlock
        if not settings.anthropic_api_key:
            logger.warning("ANTHROPIC_API_KEY not set")
            return None
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        block = response.content[0]
        return block.text if isinstance(block, TextBlock) else None
    except Exception:
        logger.exception("Anthropic request failed")
        return None
