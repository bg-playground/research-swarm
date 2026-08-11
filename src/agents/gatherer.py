"""Gatherer agent – scrapes pages for clean markdown via Firecrawl (parallel + retry)."""

from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Literal, Optional, Tuple

from langchain_core.messages import AIMessage
from langgraph.types import Command

from src.state import ResearchState, Source
from src.tools.firecrawl_tools import scrape_url
from src.utils.circuit_breaker import CircuitOpenError

# Safety / cost limit – easy to raise later
MAX_SCRAPES_PER_TURN = 3
MAX_WORKERS = 3

# Short backoff before the gatherer-level retry pass
RETRY_BASE_DELAY = 1.5  # seconds
RETRY_JITTER = 0.75


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
        return src.url, None, f"API_KEY_MISSING::{exc}"
    except CircuitOpenError as exc:
        return src.url, None, f"CIRCUIT_OPEN::{exc}"
    except Exception as exc:
        return src.url, None, f"scrape failed for {src.url}: {exc}"


def _run_batch(
    batch: List[Source],
    updated_by_url: dict[str, Source],
    errors: List[str],
) -> Tuple[int, int, bool, List[Source]]:
    """
    Run a parallel scrape batch.

    Returns (scraped_count, failed_count, api_key_missing, failed_sources).
    """
    scraped_count = 0
    failed_count = 0
    api_key_missing = False
    failed_sources: List[Source] = []

    if not batch:
        return 0, 0, False, []

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(batch))) as executor:
        futures = {executor.submit(_scrape_one, src): src for src in batch}

        for future in as_completed(futures):
            src = futures[future]
            url, result, err = future.result()

            if err and (err.startswith("API_KEY_MISSING::") or err.startswith("CIRCUIT_OPEN::")):
                api_key_missing = True
                errors.append(err.split("::", 1)[1])
                for f in futures:
                    f.cancel()
                break

            if result is not None:
                updated_by_url[url] = result
                scraped_count += 1
            else:
                failed_count += 1
                failed_sources.append(src)
                if err:
                    errors.append(f"Gatherer: {err}")

    return scraped_count, failed_count, api_key_missing, failed_sources


def gatherer_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """
    Gatherer specialist.

    Scrapes the most promising sources that still lack markdown content,
    running up to MAX_SCRAPES_PER_TURN requests in parallel.
    Failed URLs get one additional retry pass within the same turn
    after a short exponential-style backoff.
    Gracefully degrades if the API key is missing or the circuit is open.
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

    scraped_count, failed_count, api_key_missing, failed_sources = _run_batch(
        to_scrape, updated_by_url, errors
    )

    if api_key_missing:
        return Command(
            goto="supervisor",
            update={
                "messages": [
                    AIMessage(
                        content=(
                            "Gatherer: FIRECRAWL_API_KEY missing or circuit open. "
                            "Skipping live scrapes."
                        )
                    )
                ],
                "errors": errors,
            },
        )

    retried_count = 0
    if failed_sources:
        retry_batch = [
            s
            for s in failed_sources
            if s.url in updated_by_url and not updated_by_url[s.url].markdown
        ]
        if retry_batch:
            delay = RETRY_BASE_DELAY + random.uniform(0, RETRY_JITTER)
            time.sleep(delay)

            extra_scraped, extra_failed, api_key_missing, _ = _run_batch(
                retry_batch, updated_by_url, errors
            )
            retried_count = extra_scraped
            scraped_count += extra_scraped
            failed_count = extra_failed

            if api_key_missing:
                return Command(
                    goto="supervisor",
                    update={
                        "messages": [
                            AIMessage(
                                content=(
                                    "Gatherer: FIRECRAWL_API_KEY missing or circuit open. "
                                    "Skipping live scrapes."
                                )
                            )
                        ],
                        "errors": errors,
                    },
                )

    updated_sources = list(updated_by_url.values())

    msg = f"Gatherer: successfully scraped {scraped_count} source(s) in parallel"
    if retried_count:
        msg += f" (including {retried_count} after backoff retry)"
    if failed_count:
        msg += f" ({failed_count} still failed)"

    updates = {
        "sources": updated_sources,
        "messages": [AIMessage(content=msg)],
        "errors": errors,
    }

    return Command(goto="supervisor", update=updates)
