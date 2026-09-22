"""Model factory: Gemini via LangChain, tuned for structured invoice work."""

from __future__ import annotations

import logging
import os
import warnings

from . import config

logger = logging.getLogger(__name__)

# Noisy-but-harmless SDK notices: this model ignores temperature, and the AFC
# note is informational. Filtered narrowly so real warnings still surface.
warnings.filterwarnings("ignore", message=".*fixed sampling defaults.*", category=UserWarning)
warnings.filterwarnings("ignore", message=".*automatic function calling.*", category=UserWarning)

_cache_ready = False


def is_agent_configured() -> bool:
    return bool(config.GEMINI_API_KEY)


def _ensure_cache() -> None:
    """Dedupe identical prompts in-process: repeat demo runs cost zero API calls."""
    global _cache_ready
    if _cache_ready:
        return
    from langchain_core.caches import InMemoryCache
    from langchain_core.globals import set_llm_cache

    set_llm_cache(InMemoryCache())
    _cache_ready = True


def get_chat_model(*, temperature: float = 0.0, max_retries: int = 2):
    """Build the Gemini chat model. Raises RuntimeError without a key (fail fast)."""
    if not is_agent_configured():
        raise RuntimeError("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set")
    # Our key wins: the SDK prefers GOOGLE_API_KEY when both are set, which
    # caused auth against a stale system-wide key.
    os.environ["GOOGLE_API_KEY"] = config.GEMINI_API_KEY
    _ensure_cache()

    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL,
        temperature=temperature,
        max_retries=max_retries,
    )
