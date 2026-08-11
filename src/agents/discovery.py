"""Discovery agent – finds candidate sources via Firecrawl Search (+ query rewrite & domain priors)."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.types import Command

from src.state import ResearchState, Source
from src.tools.firecrawl_tools import search_web
from src.utils.circuit_breaker import CircuitOpenError
from src.utils.logging_setup import get_logger
from src.utils.query_rewrite import build_search_queries
from src.utils.source_ranking import apply_domain_priors

log = get_logger("research_swarm.discovery")

MAX_NEW_SOURCES = 8
PER_QUERY_LIMIT = 5


def discovery_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """
    Discovery specialist.

    1. Expand the research goal into 1–3 targeted search queries (heuristics).
    2. Run Firecrawl Search for each query.
    3. Deduplicate, apply domain priors (boost docs/github, demote social/video), rank.
    4. Return the best new sources to the supervisor.
    """
    goal = state.get("goal", "unknown goal")
    existing_sources = list(state.get("sources", []))
    existing_urls = {s.url for s in existing_sources}
    errors = list(state.get("errors", []))

    new_sources: list[Source] = []
    message = ""
    queries = build_search_queries(goal, max_queries=3)

    try:
        collected: list[Source] = []
        for q in queries:
            try:
                batch = search_web(q, limit=PER_QUERY_LIMIT, scrape=False)
                collected.extend(batch)
                log.info("search query=%r hits=%s", q[:80], len(batch))
            except CircuitOpenError:
                raise
            except ValueError:
                raise
            except Exception as exc:
                errors.append(f"Discovery query failed ({q[:60]}...): {exc}")
                log.warning("query failed q=%r err=%s", q[:80], exc)

        seen: set[str] = set()
        unique: list[Source] = []
        for s in collected:
            if not s.url or s.url in existing_urls or s.url in seen:
                continue
            seen.add(s.url)
            unique.append(s)

        ranked = apply_domain_priors(unique)
        new_sources = ranked[:MAX_NEW_SOURCES]

        message = (
            f"Discovery: {len(queries)} query variant(s) → "
            f"{len(unique)} unique hit(s) → kept top {len(new_sources)} after domain ranking."
        )
        log.info(
            "search ok queries=%s unique=%s kept=%s total=%s",
            len(queries),
            len(unique),
            len(new_sources),
            len(existing_sources) + len(new_sources),
        )
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
