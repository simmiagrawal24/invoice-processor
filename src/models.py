"""Model factory: provider dropdown (Gemini / OpenAI / Anthropic) via LangChain.

- Server keys come from env (.env); a per-session key + model ID from the UI
  overrides them and is never stored.
- Construction is offline-safe; failures raise RuntimeError with a plain message.
"""

from __future__ import annotations

import logging
import os
import warnings

from . import config

logger = logging.getLogger(__name__)

# Noisy-but-harmless SDK notices, filtered narrowly so real warnings surface.
warnings.filterwarnings("ignore", message=".*fixed sampling defaults.*", category=UserWarning)
warnings.filterwarnings("ignore", message=".*automatic function calling.*", category=UserWarning)

PROVIDERS = ("gemini", "openai", "anthropic")

_cache_ready = False


def default_model(provider: str) -> str:
    return {
        "gemini": config.GEMINI_MODEL,
        "openai": config.OPENAI_MODEL,
        "anthropic": config.ANTHROPIC_MODEL,
    }[provider]


def server_key(provider: str) -> str:
    return {
        "gemini": config.GEMINI_API_KEY,
        "openai": config.OPENAI_API_KEY,
        "anthropic": config.ANTHROPIC_API_KEY,
    }[provider]


def normalize_provider(name: str | None) -> str:
    provider = (name or config.LLM_PROVIDER).strip().lower()
    if provider not in PROVIDERS:
        raise RuntimeError(f"Unknown provider {name!r} — choose one of {', '.join(PROVIDERS)}")
    return provider


def is_configured(provider: str | None = None) -> bool:
    try:
        return bool(server_key(normalize_provider(provider)))
    except RuntimeError:
        return False


def is_agent_configured() -> bool:
    return is_configured("gemini")


def _ensure_cache() -> None:
    """Dedupe identical prompts in-process: repeat demo runs cost zero API calls."""
    global _cache_ready
    if _cache_ready:
        return
    from langchain_core.caches import InMemoryCache
    from langchain_core.globals import set_llm_cache

    set_llm_cache(InMemoryCache())
    _cache_ready = True


def get_chat_model(
    provider: str | None = None,
    *,
    temperature: float = 0.0,
    max_retries: int = 2,
    api_key: str | None = None,
    model: str | None = None,
):
    """Build a provider chat model. Explicit api_key/model win (per-session BYOK)."""
    provider = normalize_provider(provider)
    key = (api_key or "").strip() or server_key(provider)
    if not key:
        raise RuntimeError(f"No API key for provider {provider!r}")
    model_name = (model or "").strip() or default_model(provider)
    _ensure_cache()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not api_key:
            # Our key wins: the SDK prefers GOOGLE_API_KEY when both are set, which
            # caused auth against a stale system-wide key.
            os.environ["GOOGLE_API_KEY"] = key
            return ChatGoogleGenerativeAI(
                model=model_name, temperature=temperature, max_retries=max_retries
            )
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            max_retries=max_retries,
            google_api_key=key,
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name, temperature=temperature, max_retries=max_retries, openai_api_key=key
        )
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model_name, temperature=temperature, max_retries=max_retries, anthropic_api_key=key
    )
