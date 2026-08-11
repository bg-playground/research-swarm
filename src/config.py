"""Configuration helpers for research-swarm."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
_env_path = _ROOT / ".env"
load_dotenv(_env_path)


def get_openai_api_key() -> str:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key or key.startswith("sk-..."):
        raise ValueError(
            "OPENAI_API_KEY is not set (or still a placeholder). "
            "Copy .env.example to .env and add a real key."
        )
    return key


def get_firecrawl_api_key() -> str | None:
    key = (os.getenv("FIRECRAWL_API_KEY") or "").strip()
    if not key or key.startswith("fc-..."):
        return None
    return key


def get_firecrawl_api_url() -> str | None:
    url = (os.getenv("FIRECRAWL_API_URL") or "").strip()
    return url or None


def get_llm_model() -> str:
    return (os.getenv("RESEARCH_SWARM_MODEL") or "gpt-4o-mini").strip()


def get_llm_temperature() -> float:
    raw = (os.getenv("RESEARCH_SWARM_TEMPERATURE") or "0").strip()
    try:
        return float(raw)
    except ValueError:
        return 0.0


def get_cache_ttl_hours() -> float:
    raw = (os.getenv("RESEARCH_SWARM_CACHE_TTL_HOURS") or "24").strip()
    try:
        return float(raw)
    except ValueError:
        return 24.0


def get_chat_model(**overrides: Any):
    from langchain_openai import ChatOpenAI

    params: dict[str, Any] = {
        "model": get_llm_model(),
        "temperature": get_llm_temperature(),
        "api_key": get_openai_api_key(),
    }
    params.update(overrides)
    return ChatOpenAI(**params)
