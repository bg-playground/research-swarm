"""Discovery agent – Firecrawl Search + optional site Map enrichment."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.types import Command

from src.state import ResearchState, Source
from src.tools.firecrawl_tools import map_site, search_web
from src.utils.circuit_breaker import CircuitOpenError
from src.utils.logging_setup import get_logger
from src.utils.query_rewrite import build_search_queries, map_roots_from_goal
from src.utils.source_ranking import apply_domain_priors

log = get_logger("research_swarm.discovery")

MAX_NEW_SOURCES = 10
PER_QUERY_LIMIT = 5
MAP_LIMIT = 15


def discovery_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """Search + optional Map enrichment for goal-named hosts."""
    goal = state.get("goal", "unknown goal")
    existing_sources = list(state.get("sources", []))
    existing_urls = {s.url for s in existing_sources}
    errors = list(state.get("errors", []))

    new_sources: list[Source] = []
    message = ""
    queries = build_search_queries(goal, max_queries=3)
    map_roots = map_roots_from_goal(goal, max_roots=2)
    map_hits = 0

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

        for root in map_roots:
            try:
                mapped = map_site(root, limit=MAP_LIMIT)
                collected.extend(mapped)
                map_hits += len(mapped)
                log.info("map root=%s links=%s", root, len(mapped))
            except CircuitOpenError:
                raise
            except ValueError:
                raise
            except Exception as exc:
                errors.append(f"Discovery map failed ({root}): {exc}")
                log.warning("map failed root=%s err=%s", root, exc)

        seen: set[str] = set()
        unique: list[Source] = []
        for s in collected:
            if not s.url or s.url in existing_urls or s.url in seen:
                continue
            seen.add(s.url)
            unique.append(s)

        ranked = apply_domain_priors(unique)
        new_sources = ranked[:MAX_NEW_SOURCES]

        map_note = (
            f", map={map_hits} link(s) from {len(map_roots)} root(s)"
            if map_roots
            else ""
        )
        message = (
            f"Discovery: {len(queries)} query variant(s) \u2192 "
            f"{len(unique)} unique hit(s){map_note} \u2192 "
            f"kept top {len(new_sources)} after domain ranking."
        )
        log.info(
            "search ok queries=%s map_roots=%s map_hits=%s unique=%s kept=%s total=%s",
            len(queries),
            len(map_roots),
            map_hits,
            len(unique),
            len(new_sources),
            len(existing_sources) + len(new_sources),
        )
    except ValueError as exc:
        errors.append(str(exc))
        message = (
            "Discovery: FIRECRAWL_API_KEY is not set. "
            "Skipping live search/map. Add the key to enable real discovery."
        )
        log.warning("missing API key: %s", exc)
    except CircuitOpenError as exc:
        errors.append(str(exc))
        message = f"Discovery: circuit breaker is open \u2013 {exc}"
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
