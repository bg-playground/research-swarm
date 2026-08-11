"""Firecrawl tool wrappers for the research-swarm.

These are thin, typed helpers around the official firecrawl-py SDK.
They normalize responses into our Source model and keep the specialist
agents simple.

Includes rate-limit retry, circuit breaker, and disk URL cache for scrapes.
"""

from __future__ import annotations

import logging
import random
import time
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar

from src.config import get_firecrawl_api_key
from src.state import Source
from src.utils.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)

DEFAULT_MARKDOWN_MAX_CHARS = 12_000

_firecrawl_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60.0,
    name="firecrawl",
)

F = TypeVar("F", bound=Callable[..., Any])


def with_rate_limit_retry(
    max_retries: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[Exception] = None
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    msg = str(exc).lower()
                    is_rate_limit = (
                        "429" in msg
                        or "rate limit" in msg
                        or "too many" in msg
                        or "rate_limit" in msg
                        or "quota" in msg
                    )
                    if not is_rate_limit or attempt == max_retries:
                        raise
                    delay = min(base_delay * (2**attempt) + random.uniform(0, 0.75), max_delay)
                    logger.warning(
                        "Rate limit detected in %s (attempt %d/%d). Backing off %.1fs... (%s)",
                        fn.__name__,
                        attempt + 1,
                        max_retries,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                    last_exc = exc
            if last_exc:
                raise last_exc
            raise RuntimeError("Unexpected retry loop exit")

        return wrapper  # type: ignore[return-value]

    return decorator


def with_circuit_breaker(fn: F) -> F:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not _firecrawl_breaker.allow_request():
            raise CircuitOpenError(_firecrawl_breaker)
        try:
            result = fn(*args, **kwargs)
            _firecrawl_breaker.record_success()
            return result
        except CircuitOpenError:
            raise
        except Exception:
            _firecrawl_breaker.record_failure()
            raise

    return wrapper  # type: ignore[return-value]


def _truncate(text: Optional[str], max_chars: int = DEFAULT_MARKDOWN_MAX_CHARS) -> Optional[str]:
    if text is None:
        return None
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n\n...[truncated]..."


def get_firecrawl_client():
    api_key = get_firecrawl_api_key()
    if not api_key:
        raise ValueError(
            "FIRECRAWL_API_KEY is not set. "
            "Add it to your .env file or environment to enable real web tools."
        )
    try:
        from firecrawl import Firecrawl
    except ImportError as exc:
        raise ImportError("firecrawl-py is not installed. Run: pip install firecrawl-py") from exc
    return Firecrawl(api_key=api_key)


@with_circuit_breaker
@with_rate_limit_retry()
def search_web(
    query: str,
    *,
    limit: int = 5,
    scrape: bool = False,
) -> List[Source]:
    client = get_firecrawl_client()
    try:
        kwargs: Dict[str, Any] = {"limit": limit}
        if scrape:
            kwargs["scrape_options"] = {"formats": ["markdown"]}
        result = client.search(query, **kwargs)

        web_results = []
        if hasattr(result, "web") and result.web is not None:
            web_results = result.web
        elif isinstance(result, dict):
            web_results = result.get("web") or result.get("data") or []
        elif isinstance(result, list):
            web_results = result

        sources: List[Source] = []
        for item in web_results or []:
            if hasattr(item, "url"):
                url = item.url
                title = getattr(item, "title", None)
                description = getattr(item, "description", None) or getattr(item, "snippet", None)
                markdown = getattr(item, "markdown", None)
            else:
                url = item.get("url")
                title = item.get("title")
                description = item.get("description") or item.get("snippet")
                markdown = item.get("markdown")
            if not url:
                continue
            sources.append(
                Source(
                    url=url,
                    title=title,
                    summary=description,
                    markdown=_truncate(markdown) if markdown else None,
                    quality_score=0.65 if markdown else 0.55,
                    source_type="search",
                    metadata={"query": query, "from_search": True},
                )
            )
        return sources
    except Exception as exc:
        logger.exception("Firecrawl search failed for query=%s", query)
        raise RuntimeError(f"Firecrawl search failed: {exc}") from exc


def scrape_url(
    url: str,
    *,
    only_main_content: bool = True,
    formats: Optional[List[str]] = None,
) -> Optional[Source]:
    """Scrape URL with disk cache. Cache hits skip network and circuit breaker."""
    from src.utils.url_cache import get_cached_source, put_cached_source

    cached = get_cached_source(url)
    if cached is not None:
        return cached

    result = _scrape_url_live(
        url, only_main_content=only_main_content, formats=formats
    )
    if result is not None:
        put_cached_source(result)
    return result


@with_circuit_breaker
@with_rate_limit_retry()
def _scrape_url_live(
    url: str,
    *,
    only_main_content: bool = True,
    formats: Optional[List[str]] = None,
) -> Optional[Source]:
    client = get_firecrawl_client()
    formats = formats or ["markdown"]
    try:
        doc = client.scrape(
            url,
            formats=formats,
            only_main_content=only_main_content,
        )
        if hasattr(doc, "markdown"):
            markdown = doc.markdown
            title = getattr(doc, "title", None) or getattr(
                getattr(doc, "metadata", None), "title", None
            )
            metadata = getattr(doc, "metadata", None) or {}
        elif isinstance(doc, dict):
            data = doc.get("data") or doc
            markdown = data.get("markdown")
            metadata = data.get("metadata") or {}
            title = metadata.get("title")
        else:
            return None
        if not markdown:
            return None
        return Source(
            url=url,
            title=title,
            markdown=_truncate(markdown),
            summary=(markdown[:300] + "...") if len(markdown) > 300 else markdown,
            quality_score=0.8,
            source_type="scrape",
            metadata={"from_scrape": True, "raw_metadata": dict(metadata) if metadata else {}},
        )
    except Exception as exc:
        logger.exception("Firecrawl scrape failed for url=%s", url)
        raise RuntimeError(f"Firecrawl scrape failed for {url}: {exc}") from exc


@with_circuit_breaker
@with_rate_limit_retry()
def map_site(url: str, *, limit: int = 20) -> List[Source]:
    client = get_firecrawl_client()
    try:
        result = client.map(url, limit=limit)
        links = []
        if hasattr(result, "links") and result.links is not None:
            links = result.links
        elif isinstance(result, dict):
            links = result.get("links") or result.get("data") or []
        elif isinstance(result, list):
            links = result
        sources: List[Source] = []
        for item in links or []:
            if hasattr(item, "url"):
                link_url = item.url
                title = getattr(item, "title", None)
            elif isinstance(item, dict):
                link_url = item.get("url")
                title = item.get("title")
            elif isinstance(item, str):
                link_url = item
                title = None
            else:
                continue
            if not link_url:
                continue
            sources.append(
                Source(
                    url=link_url,
                    title=title,
                    quality_score=0.5,
                    source_type="map",
                    metadata={"from_map": True, "root": url},
                )
            )
        return sources
    except Exception as exc:
        logger.exception("Firecrawl map failed for url=%s", url)
        raise RuntimeError(f"Firecrawl map failed for {url}: {exc}") from exc


@with_circuit_breaker
@with_rate_limit_retry()
def crawl_site(
    url: str,
    *,
    limit: int = 10,
    only_main_content: bool = True,
) -> List[Source]:
    client = get_firecrawl_client()
    try:
        result = client.crawl(
            url,
            limit=limit,
            scrape_options={"formats": ["markdown"], "onlyMainContent": only_main_content},
        )
        pages = []
        if hasattr(result, "data") and result.data is not None:
            pages = result.data
        elif isinstance(result, dict):
            pages = result.get("data") or result.get("pages") or []
        elif isinstance(result, list):
            pages = result
        sources: List[Source] = []
        for page in pages or []:
            if hasattr(page, "markdown"):
                markdown = page.markdown
                page_url = getattr(page, "url", None) or getattr(page, "sourceURL", url)
                title = getattr(page, "title", None)
            elif isinstance(page, dict):
                markdown = page.get("markdown")
                page_url = page.get("url") or page.get("sourceURL") or url
                metadata = page.get("metadata") or {}
                title = metadata.get("title")
            else:
                continue
            if not markdown:
                continue
            sources.append(
                Source(
                    url=page_url,
                    title=title,
                    markdown=_truncate(markdown),
                    summary=(markdown[:300] + "...") if len(markdown) > 300 else markdown,
                    quality_score=0.75,
                    source_type="crawl",
                    metadata={"from_crawl": True, "root": url},
                )
            )
        return sources
    except Exception as exc:
        logger.exception("Firecrawl crawl failed for url=%s", url)
        raise RuntimeError(f"Firecrawl crawl failed for {url}: {exc}") from exc
