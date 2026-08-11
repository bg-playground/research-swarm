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
from src.utils.logging_setup import get_logger

log = get_logger("research_swarm.gatherer")

MAX_SCRAPES_PER_TURN = 5
MAX_WORKERS = 5

RETRY_BASE_DELAY = 1.5
RETRY_JITTER = 0.75


def _scrape_one(src: Source) -> Tuple[str, Optional[Source], Optional[str]]:
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
                failed_count += 1
                failed_sources.append(src)
                continue

            if result is not None:
                updated_by_url[url] = result
                scraped_count += 1
            else:
                failed_count += 1
                failed_sources.append(src)
                if err:
                    errors.append(err)

    return scraped_count, failed_count, api_key_missing, failed_sources


def gatherer_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    sources = list(state.get("sources", []))
    errors = list(state.get("errors", []))

    if not sources:
        return Command(
            goto="supervisor",
            update={
                "messages": [AIMessage(content="Gatherer: no sources to scrape.")],
                "errors": errors,
            },
        )

    pending = [s for s in sources if not s.markdown]
    pending.sort(key=lambda s: s.quality_score, reverse=True)
    batch = pending[:MAX_SCRAPES_PER_TURN]

    if not batch:
        return Command(
            goto="supervisor",
            update={
                "messages": [
                    AIMessage(
                        content=f"Gatherer: all {len(sources)} source(s) already have content."
                    )
                ],
                "errors": errors,
            },
        )

    updated_by_url = {s.url: s for s in sources}
    scraped, failed, key_missing, failed_sources = _run_batch(batch, updated_by_url, errors)

    retried = 0
    if failed_sources and not key_missing:
        delay = RETRY_BASE_DELAY + random.uniform(0, RETRY_JITTER)
        time.sleep(delay)
        s2, f2, key_missing2, still_failed = _run_batch(failed_sources, updated_by_url, errors)
        scraped += s2
        failed = f2
        retried = len(failed_sources)
        key_missing = key_missing or key_missing2

    new_sources = list(updated_by_url.values())
    msg = (
        f"Gatherer: scraped={scraped} retried={retried} failed={failed} "
        f"total_sources={len(new_sources)}"
    )
    log.info("scraped=%s retried=%s failed=%s total_sources=%s", scraped, retried, failed, len(new_sources))

    return Command(
        goto="supervisor",
        update={
            "sources": new_sources,
            "messages": [AIMessage(content=msg)],
            "errors": errors,
        },
    )
