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
            "the", "a", "an", "and", "or", "for", "of", "to", "in", "on", "with", "from",
            "summarize", "summary", "compare", "explain", "what", "how", "please",
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


def map_roots_from_goal(goal: str, *, max_roots: int = 2) -> list[str]:
    """HTTPS roots for Firecrawl Map; prefers docs./developer./api. hosts."""
    sites = extract_site_hints(goal)
    if not sites:
        return []

    def _rank_key(host: str) -> tuple[int, str]:
        h = host.lower()
        if h.startswith(("docs.", "developer.", "developers.", "api.", "dev.")):
            return (0, h)
        if "docs" in h or "developer" in h:
            return (1, h)
        return (2, h)

    ordered = sorted(sites, key=_rank_key)
    roots: list[str] = []
    seen: set[str] = set()
    for host in ordered:
        host = host.lower().removeprefix("www.")
        if host.startswith("http://") or host.startswith("https://"):
            root = host.rstrip("/")
        else:
            root = f"https://{host}"
        key = root.lower()
        if key in seen:
            continue
        seen.add(key)
        roots.append(root)
        if len(roots) >= max_roots:
            break
    return roots


def primary_domain_from_goal(goal: str) -> str | None:
    roots = map_roots_from_goal(goal, max_roots=1)
    return roots[0] if roots else None
