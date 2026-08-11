"""Extractor agent – pulls structured facts from collected markdown content."""

from __future__ import annotations

from typing import List, Literal, Set

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from src.config import get_chat_model
from src.state import ExtractedFact, ResearchState, Source
from src.utils.logging_setup import get_logger

log = get_logger("research_swarm.extractor")

MAX_SOURCES_PER_TURN = 5
SNIPPET_CHARS = 3000


class ExtractionResult(BaseModel):
    facts: List[ExtractedFact] = Field(default_factory=list)


EXTRACTOR_SYSTEM = """You are a careful research extractor for a multi-agent research system.

From the provided web content, extract only clear, concrete facts that help answer the research goal.

Rules:
1. Prefer specific, verifiable claims (numbers, dates, product names, feature lists, pricing tiers, comparisons).
2. Every fact MUST include source_urls taken from the provided Source URL lines — never invent URLs.
3. Every fact MUST include an evidence field: a short verbatim quote (1-2 sentences max)
   copied from the source markdown that supports the claim. Do not paraphrase in evidence.
   If you cannot find a supporting quote, omit that fact entirely.
4. Set confidence between 0.5 and 0.95 based on how explicit the source is.
   Prefer higher confidence when the evidence quote is direct and unambiguous.
5. Use a short category when useful (e.g. pricing, features, limits, company, comparison).
6. Do not invent information. If the content is thin, return fewer facts.
7. Avoid duplicate claims; merge near-duplicates into one fact with multiple source_urls when possible.
8. Keep claim text concise (one sentence). Put detail in value as a short string
   (serialize numbers, short lists, or key points as plain text).
"""


def _dedupe_facts(existing: List[ExtractedFact], new: List[ExtractedFact]) -> List[ExtractedFact]:
    seen: Set[str] = {f.claim.strip().lower()[:120] for f in existing}
    out: List[ExtractedFact] = []
    for f in new:
        key = f.claim.strip().lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _pending_sources(sources: List[Source], already: Set[str]) -> List[Source]:
    pending = [s for s in sources if s.markdown and s.url not in already]
    pending.sort(key=lambda s: s.quality_score, reverse=True)
    return pending


def extractor_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """Extractor specialist (incremental + claim-evidence pairing)."""
    sources = state.get("sources", [])
    existing_facts = list(state.get("extracted_facts", []))
    already = set(state.get("extracted_urls") or [])
    goal = state.get("goal", "unknown")
    errors = list(state.get("errors", []))

    pending = _pending_sources(sources, already)

    if not pending:
        contentful = sum(1 for s in sources if s.markdown)
        msg = (
            "Extractor: no new sources to process "
            f"(contentful={contentful}, already_extracted={len(already)}). Skipping."
        )
        log.info("incremental skip contentful=%s already=%s", contentful, len(already))
        return Command(
            goto="supervisor",
            update={"messages": [AIMessage(content=msg)]},
        )

    batch = pending[:MAX_SOURCES_PER_TURN]
    context_parts = []
    for s in batch:
        snippet = (s.markdown or "")[:SNIPPET_CHARS]
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
        + f"\n\nWeb content (new sources only):\n{context}"
    )

    new_facts: List[ExtractedFact] = []
    newly_extracted: List[str] = []
    try:
        llm = get_chat_model(temperature=0)
        structured = llm.with_structured_output(ExtractionResult, method="function_calling")
        result: ExtractionResult = structured.invoke(
            [SystemMessage(content=EXTRACTOR_SYSTEM), HumanMessage(content=human)]
        )
        raw_facts = result.facts or []
        grounded = [
            f
            for f in raw_facts
            if (f.claim or "").strip()
            and (f.evidence or "").strip()
            and f.source_urls
        ]
        skipped_ungrounded = len(raw_facts) - len(grounded)
        new_facts = _dedupe_facts(existing_facts, grounded)
        newly_extracted = [s.url for s in batch]
        log.info(
            "extracted %s new fact(s) from %s new source(s) "
            "(pending=%s already=%s skipped_dup=%s ungrounded=%s)",
            len(new_facts),
            len(batch),
            len(pending),
            len(already),
            len(grounded) - len(new_facts),
            skipped_ungrounded,
        )
    except Exception as exc:
        errors.append(f"Extractor LLM call failed: {exc}")
        log.exception("extractor LLM failed")
        new_facts = []
        newly_extracted = []

    updates = {
        "extracted_facts": existing_facts + new_facts,
        "extracted_urls": list(already) + newly_extracted,
        "messages": [
            AIMessage(
                content=(
                    f"Extractor: produced {len(new_facts)} grounded fact(s) from "
                    f"{len(batch)} new source(s) "
                    f"({len(pending) - len(batch)} still pending next turn)."
                )
            )
        ],
        "errors": errors,
    }

    return Command(goto="supervisor", update=updates)
