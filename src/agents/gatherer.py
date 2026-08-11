"""Gatherer agent stub – scrapes / crawls pages for clean content."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.types import Command

from src.state import ResearchState, Source


def gatherer_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """
    Gatherer specialist (stub).

    In the real implementation this will call Firecrawl Scrape / Crawl / Interact
    to obtain clean markdown for the most promising sources.
    """
    sources = list(state.get("sources", []))
    goal = state.get("goal", "")

    if not sources:
        return Command(
            goto="supervisor",
            update={
                "messages": [
                    AIMessage(
                        content="Gatherer (stub): no sources available yet. Returning to supervisor."
                    )
                ],
                "errors": state.get("errors", [])
                + ["Gatherer called with empty sources list"],
            },
        )

    # TODO: Replace with real Firecrawl scrape / batch_scrape / crawl
    # Prefer sources that still lack markdown content.

    updated_sources: list[Source] = []
    scraped_count = 0

    for src in sources:
        if src.markdown is None or src.markdown.strip() == "":
            # Simulate a successful scrape
            new_src = src.model_copy(
                update={
                    "markdown": (
                        f"# Stub content for {src.url}\n\n"
                        f"This is placeholder markdown that would normally be returned "
                        f"by Firecrawl for the research goal: {goal[:80]}...\n\n"
                        "Replace this with a real `firecrawl.scrape()` or crawl call."
                    ),
                    "summary": f"Stub summary of content from {src.url}",
                    "quality_score": min(src.quality_score + 0.15, 0.95),
                    "source_type": "scrape",
                    "metadata": {**src.metadata, "stub_scraped": True},
                }
            )
            updated_sources.append(new_src)
            scraped_count += 1
        else:
            updated_sources.append(src)

    updates = {
        "sources": updated_sources,
        "messages": [
            AIMessage(
                content=f"Gatherer (stub): simulated scrape on {scraped_count} source(s)."
            )
        ],
    }

    return Command(goto="supervisor", update=updates)
