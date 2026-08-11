"""Build a Mermaid citation graph from sources and grounded facts."""

from __future__ import annotations

import re
from typing import List, Sequence

from src.state import ExtractedFact, Source


def _safe_id(prefix: str, index: int) -> str:
    return f"{prefix}{index}"


def _label(text: str, max_len: int = 42) -> str:
    cleaned = re.sub(r"[\r\n\"\[\]{}|]+", " ", (text or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1] + "\u2026"
    return cleaned or "untitled"


def build_mermaid_citation_graph(
    sources: Sequence[Source],
    facts: Sequence[ExtractedFact],
    *,
    max_sources: int = 8,
    max_facts: int = 10,
) -> str:
    """Return a Mermaid flowchart linking sources \u2192 facts."""
    src_list = list(sources)[:max_sources]
    fact_list = list(facts)[:max_facts]

    if not src_list and not fact_list:
        return (
            "```mermaid\nflowchart LR\n"
            '  empty["No sources or facts yet"]\n```'
        )

    url_to_sid: dict[str, str] = {}
    lines: List[str] = ["flowchart LR"]

    for i, s in enumerate(src_list, 1):
        sid = _safe_id("S", i)
        url_to_sid[s.url] = sid
        title = _label(s.title or s.url)
        lines.append(f'  {sid}["{title}"]')

    for j, f in enumerate(fact_list, 1):
        fid = _safe_id("F", j)
        claim = _label(f.claim, max_len=48)
        lines.append(f'  {fid}("{claim}")')
        linked = False
        for url in f.source_urls or []:
            sid = url_to_sid.get(url)
            if sid:
                lines.append(f"  {sid} --> {fid}")
                linked = True
        if not linked and src_list:
            lines.append(f"  {_safe_id('S', 1)} -.-> {fid}")

    lines.append("")
    lines.append("  classDef source fill:#1e293b,stroke:#38bdf8,color:#e2e8f0")
    lines.append("  classDef fact fill:#0f766e,stroke:#5eead4,color:#ecfdf5")
    if src_list:
        sids = ",".join(_safe_id("S", i) for i in range(1, len(src_list) + 1))
        lines.append(f"  class {sids} source")
    if fact_list:
        fids = ",".join(_safe_id("F", j) for j in range(1, len(fact_list) + 1))
        lines.append(f"  class {fids} fact")

    body = "\n".join(lines)
    return f"```mermaid\n{body}\n```
