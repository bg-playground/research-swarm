"""Configuration helpers for research-swarm."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root if present
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
