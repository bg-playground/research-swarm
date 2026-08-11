"""Discovery agent stub – finds candidate sources via search / map."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.types import Command

from src.state import ResearchState, Source


def discovery_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """
    Discovery specialist (stub).

    In the real implementation this will call Firecrawl Search + Map
    to locate high-quality starting points for the research goal.
    """
    goal = state.get("goal", "unknown goal")
    existing_sources = state.get("sources", [])

    # TODO: Replace with real Firecrawl search + map calls
    # Example future shape:
    #   results = firecrawl.search(query=goal, limit=5)
    #   mapped = firecrawl.map(url=some_url)

    # Stub: invent a couple of plausible sources so the rest of the graph can run
    new_sources = [
        Source(
            url="https://example.com/research-topic",
            title=f"Overview related to: {goal[:60]}",
            summary="Stub discovery result – replace with real Firecrawl Search.",
            quality_score=0.6,
            source_type="search",
            metadata={"stub": True, "query": goal},
        ),
        Source(
            url="https://example.org/deep-dive",
            title="Secondary source (stub)",
            summary="Another placeholder discovered source.",
            quality_score=0.55,
            source_type="search",
            metadata={"stub": True},
        ),
    ]

    # Avoid obvious duplicates in the stub
    existing_urls = {s.url for s in existing_sources}
    unique_new = [s for s in new_sources if s.url not in existing_urls]

    updates = {
        "sources": existing_sources + unique_new,
        "messages": [
            AIMessage(
                content=(
                    f"Discovery (stub): found {len(unique_new)} new candidate source(s) "
                    f"for goal '{goal[:80]}'."
                )
            )
        ],
    }

    return Command(goto="supervisor", update=updates)
