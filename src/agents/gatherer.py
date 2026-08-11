"""Gatherer agent – scrapes pages for clean markdown via Firecrawl (parallel)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal, Optional, Tuple

from langchain_core.messages import AIMessage
from langgraph.types import Command

from src.state import ResearchState, Source
from src.tools.firecrawl_tools import scrape_url

# Safety / cost limit – easy to raise later
MAX_SCRAPES_PER_TURN = 3
MAX_WORKERS = 3


def _scrape_one(src: Source) -> Tuple[str, Optional[Source], Optional[str]]:
    """
    Worker helper. Returns (url, result_or_None, error_message_or_None).
    """
    try:
        result = scrape_url(src.url, only_main_content=True)
        if result and result.markdown:
            merged = result.model_copy(
                update={
                    "quality_score": max(src.quality_score, result.quality_score),
                    "metadata": {**src.metadata, **result.metadata, "scraped": True},
                }
            )
            return src.url, merged, None
        return src.url, None, f"no useful content returned for {src.url}"
    except ValueError as exc:
        # Missing API key – surface specially
        return src.url, None, f"API_KEY_MISSING::{exc}"
    except Exception as exc:
        return src.url, None, f"scrape failed for {src.url}: {exc}"


def gatherer_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """
    Gatherer specialist.

    Scrapes the most promising sources that still lack markdown content,
    running up to MAX_SCRAPES_PER_TURN requests in parallel via a thread pool.
    Gracefully degrades if the API key is missing or individual scrapes fail.
    """
    sources = list(state.get("sources", []))
    errors = list(state.get("errors", []))

    if not sources:
        return Command(
            goto="supervisor",
            update={
                "messages": [
                    AIMessage(content="Gatherer: no sources available yet. Returning to supervisor.")
                ],
                "errors": errors + ["Gatherer called with empty sources list"],
            },
        )

    # Prefer sources that still need content, highest quality first
    candidates = sorted(
        [s for s in sources if not s.markdown],
        key=lambda s: s.quality_score,
        reverse=True,
    )

    to_scrape = candidates[:MAX_SCRAPES_PER_TURN]

    if not to_scrape:
        return Command(
            goto="supervisor",
            update={
                "messages": [
                    AIMessage(content="Gatherer: all current sources already have content.")
                ]
            },
        )

    updated_by_url: dict[str, Source] = {s.url: s for s in sources}
    scraped_count = 0
    failed_count = 0
    api_key_missing = False

    # Parallel scrape
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(to_scrape))) as executor:
        futures = {executor.submit(_scrape_one, src): src for src in to_scrape}

        for future in as_completed(futures):
            url, result, err = future.result()

            if err and err.startswith("API_KEY_MISSING::"):
                api_key_missing = True
                errors.append(err.split("::", 1)[1])
                # Cancel remaining work – no point continuing without a key
                for f in futures:
                    f.cancel()
                break

            if result is not None:
                updated_by_url[url] = result
                scraped_count += 1
            else:
                failed_count += 1
                if err:
                    errors.append(f"Gatherer: {err}")

    if api_key_missing:
        return Command(
            goto="supervisor",
            update={
                "messages": [
                    AIMessage(
                        content=(
                            "Gatherer: FIRECRAWL_API_KEY is not set. "
                            "Skipping live scrapes."
                        )
                    )
                ],
                "errors": errors,
            },
        )

    updated_sources = list(updated_by_url.values())

    msg = f"Gatherer: successfully scraped {scraped_count} source(s) in parallel"
    if failed_count:
        msg += f" ({failed_count} failed)"

    updates = {
        "sources": updated_sources,
        "messages": [AIMessage(content=msg)],
        "errors": errors,
    }

    return Command(goto="supervisor", update=updates)
