"""Disk-backed URL content cache for Firecrawl scrape results.

Reduces API cost and latency on re-runs of the same research goals.
Disabled when RESEARCH_SWARM_CACHE_DISABLED is truthy.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from src.state import Source

log = logging.getLogger(__name__)

_DEFAULT_DIR = ".cache/research_swarm"
_DEFAULT_TTL_HOURS = 24.0


def cache_enabled() -> bool:
    raw = (os.getenv("RESEARCH_SWARM_CACHE_DISABLED") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return False
    return True


def cache_dir() -> Path:
    raw = (os.getenv("RESEARCH_SWARM_CACHE_DIR") or "").strip()
    if raw:
        path = Path(raw).expanduser()
    else:
        root = Path(__file__).resolve().parents[2]
        path = root / _DEFAULT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_ttl_seconds() -> float:
    raw = (os.getenv("RESEARCH_SWARM_CACHE_TTL_HOURS") or "").strip()
    try:
        hours = float(raw) if raw else _DEFAULT_TTL_HOURS
    except ValueError:
        hours = _DEFAULT_TTL_HOURS
    return max(0.0, hours) * 3600.0


def _normalize_url(url: str) -> str:
    return (url or "").strip()


def _key_for_url(url: str) -> str:
    return hashlib.sha256(_normalize_url(url).encode("utf-8")).hexdigest()


def _path_for_url(url: str) -> Path:
    return cache_dir() / f"{_key_for_url(url)}.json"


def get_cached_source(url: str) -> Optional[Source]:
    if not cache_enabled():
        return None
    url = _normalize_url(url)
    if not url:
        return None

    path = _path_for_url(url)
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("cache read failed path=%s err=%s", path, exc)
        return None

    cached_at = float(data.get("cached_at") or 0)
    ttl = cache_ttl_seconds()
    if ttl > 0 and cached_at and (time.time() - cached_at) > ttl:
        log.debug("cache expired url=%s", url)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None

    try:
        source = Source(
            url=data.get("url") or url,
            title=data.get("title"),
            markdown=data.get("markdown"),
            summary=data.get("summary"),
            quality_score=float(data.get("quality_score") or 0.7),
            source_type=data.get("source_type") or "scrape",
            metadata={
                **(data.get("metadata") or {}),
                "from_cache": True,
                "cached_at": cached_at,
            },
        )
    except Exception as exc:
        log.warning("cache decode failed url=%s err=%s", url, exc)
        return None

    if not source.markdown:
        return None

    log.info("cache hit url=%s", url[:120])
    return source


def put_cached_source(source: Source) -> None:
    if not cache_enabled():
        return
    if not source or not source.url or not source.markdown:
        return

    path = _path_for_url(source.url)
    payload: dict[str, Any] = {
        "url": source.url,
        "title": source.title,
        "markdown": source.markdown,
        "summary": source.summary,
        "quality_score": source.quality_score,
        "source_type": source.source_type,
        "metadata": {
            k: v
            for k, v in (source.metadata or {}).items()
            if k not in {"from_cache", "cached_at"}
        },
        "cached_at": time.time(),
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        log.debug("cache store url=%s path=%s", source.url[:120], path.name)
    except OSError as exc:
        log.warning("cache write failed url=%s err=%s", source.url[:120], exc)


def clear_cache() -> int:
    root = cache_dir()
    removed = 0
    for p in root.glob("*.json"):
        try:
            p.unlink()
            removed += 1
        except OSError:
            pass
    return removed
