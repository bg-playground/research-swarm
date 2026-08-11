"""Firecrawl tool wrappers for the research-swarm.

These are thin, typed helpers around the official firecrawl-py SDK.
They normalize responses into our Source model and keep the specialist
agents simple.

Includes a simple rate-limit retry decorator (exponential backoff + jitter).
"""

from __future__ import annotations

import logging
import random
import time
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar

from src.config import get_firecrawl_api_key
from src.state import Source

logger = logging.getLogger(__name__)

# Soft limit to keep markdown from exploding context windows
DEFAULT_MARKDOWN_MAX_CHARS = 12_000

F = TypeVar("F", bound=Callable[..., Any])


def with_rate_limit_retry(
    max_retries: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> Callable[[F], F]:
    """
    Decorator that retries on rate-limit style errors with exponential backoff + jitter.

    Detects common signals: HTTP 429, "rate limit", "too many requests", etc.
    """

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
                        "Rate limit detected in %s (attempt %d/%d). "
                        "Backing off %.1fs… (%s)",
                        fn.__name__,
                        attempt + 1,
                        max_retries,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                    last_exc = exc
            # Should never reach here, but just in case
            if last_exc:
                raise last_exc
            raise RuntimeError("Unexpected retry loop exit")

        return wrapper  # type: ignore[return-value]

    return decorator


def _truncate(text: Optional[str], max_chars: int = DEFAULT_MARKDOWN_MAX_CHARS) -> Optional[str]:
    if text is None:
        return None
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n\n...[truncated]..."


def get_firecrawl_client():
    """
    Return an initialized Firecrawl client.

    Raises ValueError if FIRECRAWL_API_KEY is not set.
    """
    api_key = get_firecrawl_api_key()
    if not api_key:
        raise ValueError(
            "FIRECRAWL_API_KEY is not set. "
            "Add it to your .env file or environment to enable real web tools."
        )

    try:
        from firecrawl import Firecrawl
    except ImportError as exc:
        raise ImportError(
            "firecrawl-py is not installed. Run: pip install firecrawl-py"
        ) from exc

    return Firecrawl(api_key=api_key)


@with_rate_limit_retry()
def search_web(
    query: str,
    *,
    limit: int = 5,
    scrape: bool = False,
) -> List[Source]:
    """
    Search the live web via Firecrawl and return a list of Source objects.

    Args:
        query: Search query.
        limit: Maximum number of results to return.
        scrape: If True, also request markdown content for each result
                (more expensive / slower).

    Returns:
        List of Source instances (may be empty on failure).
    """
    client = get_firecrawl_client()

    try:
        kwargs: Dict[str, Any] = {"limit": limit}
        if scrape:
            kwargs["scrape_options"] = {"formats": ["markdown"]}

        result = client.search(query, **kwargs)

        # Handle both object-style and dict-style responses
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


@with_rate_limit_retry()
def scrape_url(
    url: str,
    *,
    only_main_content: bool = True,
    formats: Optional[List[str]] = None,
) -> Optional[Source]:
    """
    Scrape a single URL and return a Source with clean markdown.

    Returns None if the scrape fails or produces no useful content.
    """
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
            summary=(markdown[:300] + "…") if len(markdown) > 300 else markdown,
            quality_score=0.8,
            source_type="scrape",
            metadata={"from_scrape": True, "raw_metadata": dict(metadata) if metadata else {}},
        )

    except Exception as exc:
        logger.exception("Firecrawl scrape failed for url=%s", url)
        raise RuntimeError(f"Firecrawl scrape failed for {url}: {exc}") from exc


@with_rate_limit_retry()
def map_site(
    url: str,
    *,
    limit: int = 20,
) -> List[Source]:
    """
    Discover URLs on a site via Firecrawl Map (fast, no full content).

    Returns lightweight Source objects (url + title when available).
    """
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


@with_rate_limit_retry()
def crawl_site(
    url: str,
    *,
    limit: int = 10,
    only_main_content: bool = True,
) -> List[Source]:
    """
    Crawl a site (or section) and return Sources with markdown content.

    Note: Crawls can be slower and more expensive. Prefer map + selective scrape
    for most research tasks.
    """
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
                    summary=(markdown[:300] + "…") if len(markdown) > 300 else markdown,
                    quality_score=0.75,
                    source_type="crawl",
                    metadata={"from_crawl": True, "root": url},
                )
            )

        return sources

    except Exception as exc:
        logger.exception("Firecrawl crawl failed for url=%s", url)
        raise RuntimeError(f"Firecrawl crawl failed for {url}: {exc}") from exc
