"""Extractor agent – pulls structured facts from collected markdown content."""

from __future__ import annotations

from typing import List, Literal, Set

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from src.config import get_chat_model
from src.state import ExtractedFact, ResearchState
from src.utils.logging_setup import get_logger

log = get_logger("research_swarm.extractor")


class ExtractionResult(BaseModel):
    facts: List[ExtractedFact] = Field(default_factory=list)


EXTRACTOR_SYSTEM = """You are a careful research extractor for a multi-agent research system.

From the provided web content, extract only clear, concrete facts that help answer the research goal.

Rules:
1. Prefer specific, verifiable claims (numbers, dates, product names, feature lists, pricing tiers, comparisons).
2. Every fact MUST include source_urls taken from the provided Source URL lines — never invent URLs.
3. Set confidence between 0.5 and 0.95 based on how explicit the source is.
4. Use a short category when useful (e.g. pricing, features, limits, company, comparison).
5. Do not invent information. If the content is thin, return fewer facts.
6. Avoid duplicate claims; merge near-duplicates into one fact with multiple source_urls when possible.
7. Keep claim text concise (one sentence). Put detail in value (string, number, or short list/dict).
"""


def _dedupe_facts(existing: List[ExtractedFact], new: List[ExtractedFact]) -> List[ExtractedFact]:
    """Drop new facts whose claim is already present (case-insensitive)."""
    seen: Set[str] = {f.claim.strip().lower()[:120] for f in existing}
    out: List[ExtractedFact] = []
    for f in new:
        key = f.claim.strip().lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def extractor_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """
    Extractor specialist.

    Uses an LLM over the collected markdown to produce typed ExtractedFact objects.
    Falls back gracefully when there is insufficient content or the LLM fails.
    """
    sources = state.get("sources", [])
    existing_facts = list(state.get("extracted_facts", []))
    goal = state.get("goal", "unknown")
    errors = list(state.get("errors", []))

    contentful = [s for s in sources if s.markdown]

    if not contentful:
        return Command(
            goto="supervisor",
            update={
                "messages": [
                    AIMessage(content="Extractor: no sources with markdown content. Skipping.")
                ]
            },
        )

    ranked = sorted(contentful, key=lambda s: s.quality_score, reverse=True)
    context_parts = []
    for s in ranked[:5]:
        snippet = (s.markdown or "")[:3000]
        context_parts.append(
            f"### Source: {s.title or s.url}\nURL: {s.url}\nQuality: {s.quality_score:.2f}\n\n{snippet}"
        )

    context = "\n\n---\n\n".join(context_parts)
    human = (
        f"Research goal:\n{goal}\n\n"
        f"Already extracted claims (do not repeat):\n"
        + (
            "\n".join(f"- {f.claim}" for f in existing_facts[:20])
            if existing_facts
            else "(none yet)"
        )
        + f"\n\nWeb content:\n{context}"
    )

    new_facts: List[ExtractedFact] = []
    try:
        llm = get_chat_model(temperature=0)
        structured = llm.with_structured_output(ExtractionResult)
        result: ExtractionResult = structured.invoke(
            [SystemMessage(content=EXTRACTOR_SYSTEM), HumanMessage(content=human)]
        )
        new_facts = _dedupe_facts(existing_facts, result.facts or [])
        log.info(
            "extracted %s new fact(s) from %s source(s) (skipped %s duplicates)",
            len(new_facts),
            len(ranked[:5]),
            len(result.facts or []) - len(new_facts),
        )
    except Exception as exc:
        errors.append(f"Extractor LLM call failed: {exc}")
        log.exception("extractor LLM failed")
        new_facts = []

    updates = {
        "extracted_facts": existing_facts + new_facts,
        "messages": [
            AIMessage(
                content=f"Extractor: produced {len(new_facts)} fact(s) from {len(contentful)} source(s)."
            )
        ],
        "errors": errors,
    }

    return Command(goto="supervisor", update=updates)
