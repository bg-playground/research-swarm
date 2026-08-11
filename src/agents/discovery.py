"""Discovery agent – finds candidate sources via Firecrawl Search (and optional Map)."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.types import Command

from src.state import ResearchState, Source
from src.tools.firecrawl_tools import search_web
from src.utils.circuit_breaker import CircuitOpenError
from src.utils.logging_setup import get_logger

log = get_logger("research_swarm.discovery")


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
        results = search_web(goal, limit=6, scrape=False)
        unique = [s for s in results if s.url not in existing_urls]
        new_sources.extend(unique)
        message = f"Discovery: found {len(unique)} new source(s) via Firecrawl Search."
        log.info("search ok new_sources=%s total=%s", len(unique), len(existing_sources) + len(unique))
    except ValueError as exc:
        errors.append(str(exc))
        message = (
            "Discovery: FIRECRAWL_API_KEY is not set. "
            "Skipping live search. Add the key to enable real discovery."
        )
        log.warning("missing API key: %s", exc)
    except CircuitOpenError as exc:
        errors.append(str(exc))
        message = f"Discovery: circuit breaker is open – {exc}"
        log.warning("circuit open: %s", exc)
    except Exception as exc:
        errors.append(f"Discovery search failed: {exc}")
        message = f"Discovery: search failed ({exc}). Returning control to supervisor."
        log.exception("search failed")

    updates = {
        "sources": existing_sources + new_sources,
        "messages": [AIMessage(content=message)],
        "errors": errors,
    }

    return Command(goto="supervisor", update=updates)
