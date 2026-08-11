"""Discovery agent – finds candidate sources via Firecrawl Search (and optional Map)."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.types import Command

from src.state import ResearchState, Source
from src.tools.firecrawl_tools import search_web


def discovery_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """
    Discovery specialist.

    Uses Firecrawl Search to locate high-quality starting points for the research goal.
    Gracefully degrades if the API key is missing or the call fails.
    """
    goal = state.get("goal", "unknown goal")
    existing_sources = list(state.get("sources", []))
    existing_urls = {s.url for s in existing_sources}
    errors = list(state.get("errors", []))

    new_sources: list[Source] = []
    message = ""

    try:
        # Primary path: live web search
        results = search_web(goal, limit=6, scrape=False)
        unique = [s for s in results if s.url not in existing_urls]
        new_sources.extend(unique)
        message = f"Discovery: found {len(unique)} new source(s) via Firecrawl Search."
    except ValueError as exc:
        # Missing API key
        errors.append(str(exc))
        message = (
            "Discovery: FIRECRAWL_API_KEY is not set. "
            "Skipping live search. Add the key to enable real discovery."
        )
    except Exception as exc:
        errors.append(f"Discovery search failed: {exc}")
        message = f"Discovery: search failed ({exc}). Returning control to supervisor."

    updates = {
        "sources": existing_sources + new_sources,
        "messages": [AIMessage(content=message)],
        "errors": errors,
    }

    return Command(goto="supervisor", update=updates)
