"""Configuration helpers for research-swarm."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root if present
_env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_env_path)


def get_openai_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY is not set")
    return key


def get_firecrawl_api_key() -> str | None:
    return os.getenv("FIRECRAWL_API_KEY")
