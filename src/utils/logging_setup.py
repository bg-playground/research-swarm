"""Lightweight structured logging + optional LangSmith tracing for research-swarm."""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

_CONFIGURED = False


def setup_logging(level: Optional[str] = None) -> None:
    """
    Configure root logging once.

    Level comes from RESEARCH_SWARM_LOG_LEVEL or defaults to INFO.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = (level or os.getenv("RESEARCH_SWARM_LOG_LEVEL") or "INFO").upper()
    log_level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(log_level)

    if log_level > logging.DEBUG:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    _CONFIGURED = True


def enable_langsmith_if_configured() -> bool:
    """
    Enable LangSmith / LangChain tracing when env is set.

    Recognized vars (standard LangSmith):
      LANGCHAIN_TRACING_V2=true
      LANGCHAIN_API_KEY=...
      LANGCHAIN_PROJECT=research-swarm   (optional)

    Returns True if tracing appears enabled.
    """
    tracing = os.getenv("LANGCHAIN_TRACING_V2", "").lower() in {"1", "true", "yes"}
    api_key = (os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY") or "").strip()

    if not tracing:
        return False

    if not api_key:
        logging.getLogger(__name__).warning(
            "LANGCHAIN_TRACING_V2 is set but LANGCHAIN_API_KEY / LANGSMITH_API_KEY is missing — tracing disabled"
        )
        return False

    if not os.getenv("LANGCHAIN_PROJECT"):
        os.environ["LANGCHAIN_PROJECT"] = "research-swarm"

    logging.getLogger(__name__).info(
        "LangSmith tracing enabled (project=%s)",
        os.environ.get("LANGCHAIN_PROJECT"),
    )
    return True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (call setup_logging first from the process entrypoint)."""
    return logging.getLogger(name)
