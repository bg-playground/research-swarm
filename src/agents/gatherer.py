"""Gatherer agent – scrapes pages for clean markdown via Firecrawl."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.types import Command

from src.state import ResearchState, Source
from src.tools.firecrawl_tools import scrape_url


def gatherer_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """
    Gatherer specialist.

    Scrapes the most promising sources that still lack markdown content.
    Limits the number of live scrapes per turn to control cost and latency.
    Gracefully degrades if the API key is missing or individual scrapes fail.
    """
    sources = list(state.get("sources", []))
    errors = list(state.get("errors", []))
    goal = state.get("goal", "")

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

    # Safety limit: only scrape a few per turn
    MAX_SCRAPES_PER_TURN = 3
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

    for src in to_scrape:
        try:
            result = scrape_url(src.url, only_main_content=True)
            if result and result.markdown:
                # Preserve original metadata / quality while adding content
                merged = result.model_copy(
                    update={
                        "quality_score": max(src.quality_score, result.quality_score),
                        "metadata": {**src.metadata, **result.metadata, "scraped": True},
                    }
                )
                updated_by_url[src.url] = merged
                scraped_count += 1
            else:
                failed_count += 1
                errors.append(f"Gatherer: no useful content returned for {src.url}")
        except ValueError as exc:
            # Missing API key – abort further attempts this turn
            errors.append(str(exc))
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
        except Exception as exc:
            failed_count += 1
            errors.append(f"Gatherer scrape failed for {src.url}: {exc}")

    updated_sources = list(updated_by_url.values())

    msg = f"Gatherer: successfully scraped {scraped_count} source(s)"
    if failed_count:
        msg += f" ({failed_count} failed)"

    updates = {
        "sources": updated_sources,
        "messages": [AIMessage(content=msg)],
        "errors": errors,
    }

    return Command(goto="supervisor", update=updates)
