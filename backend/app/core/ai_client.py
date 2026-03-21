import logging
from functools import lru_cache

import anthropic
from anthropic.types import TextBlock

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_ai_client() -> anthropic.Anthropic | None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — AI features will use fallback logic")
        return None
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def ai_complete(system: str, prompt: str, max_tokens: int = 2048) -> str | None:
    client = get_ai_client()
    if client is None:
        return None
    settings = get_settings()
    response = client.messages.create(
        model=settings.ai_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    block = response.content[0]
    return block.text if isinstance(block, TextBlock) else None
