"""Heuristic search-query expansion for the discovery agent.

No LLM required — keeps discovery usable without OPENAI_API_KEY and makes
behavior predictable in tests.
"""

from __future__ import annotations

import re

_DOCS_HINTS = re.compile(
    r"\b(docs?|documentation|api\s*reference|reference\s*docs?|developer\s*guide|"
    r"getting\s*started|sdk|openapi|swagger)\b",
    re.I,
)

_DOMAIN_IN_GOAL = re.compile(
    r"\b(?:https?://)?(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)/?\b",
    re.I,
)
_SITE_OPERATOR = re.compile(r"\bsite:(\S+)", re.I)


def _clean_goal(goal: str) -> str:
    return re.sub(r"\s+", " ", (goal or "").strip())


def extract_site_hints(goal: str) -> list[str]:
    """Return hostnames the user already pointed at (site: or bare domains)."""
    hints: list[str] = []
    for m in _SITE_OPERATOR.finditer(goal or ""):
        host = m.group(1).strip().strip("/").lower().removeprefix("www.")
        if host and host not in hints:
            hints.append(host)
    for m in _DOMAIN_IN_GOAL.finditer(goal or ""):
        host = m.group(1).lower().removeprefix("www.")
        if host.count(".") >= 1 and host not in hints:
            hints.append(host)
    return hints[:4]


def build_search_queries(goal: str, *, max_queries: int = 3) -> list[str]:
    """
    Expand a research goal into 1–3 search queries.

    Strategy:
    1. Always keep the original goal (cleaned).
    2. If goal mentions docs/API, add a documentation-biased query.
    3. If a domain appears, add a site:-scoped query for that domain.
    """
    goal = _clean_goal(goal)
    if not goal:
        return ["software research overview"]

    queries: list[str] = [goal]
    sites = extract_site_hints(goal)

    if _DOCS_HINTS.search(goal) or sites:
        if sites:
            primary = sites[0]
            docs_host = primary if primary.startswith("docs.") else f"docs.{primary}"
            q_docs = f"site:{docs_host} {goal}"
            if q_docs not in queries:
                queries.append(q_docs)
            q_site = f"site:{primary} {goal}"
            if q_site not in queries and primary != docs_host:
                queries.append(q_site)
        else:
            q = f"{goal} official documentation API reference"
            if q not in queries:
                queries.append(q)

    if len(queries) < 2:
        filler = {
            "the", "a", "an", "and", "or", "for", "of", "to", "in", "on", "with",
            "from", "summarize", "summary", "compare", "explain", "what", "how", "please",
        }
        tokens = [t for t in re.findall(r"[A-Za-z0-9._-]+", goal) if t.lower() not in filler]
        if len(tokens) >= 3:
            short = " ".join(tokens[:8])
            if short.lower() != goal.lower():
                queries.append(short)

    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = q.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= max_queries:
            break
    return out


def primary_domain_from_goal(goal: str) -> str | None:
    """Best-effort primary domain for optional map follow-up."""
    sites = extract_site_hints(goal)
    if not sites:
        return None
    host = sites[0]
    if not host.startswith("http"):
        return f"https://{host}"
    return host
