"""Extractor agent – pulls structured facts from collected markdown content."""

from __future__ import annotations

from typing import List, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from pydantic import BaseModel, Field

from src.state import ExtractedFact, ResearchState


class ExtractionResult(BaseModel):
    facts: List[ExtractedFact] = Field(default_factory=list)


def extractor_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """
    Extractor specialist.

    Uses an LLM over the collected markdown to produce typed ExtractedFact objects.
    Falls back gracefully when there is insufficient content.
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

    # Build a compact context (limit total size)
    context_parts = []
    for s in contentful[:4]:  # max 4 sources per turn
        snippet = (s.markdown or "")[:2500]
        context_parts.append(f"### Source: {s.title or s.url}\nURL: {s.url}\n\n{snippet}")

    context = "\n\n---\n\n".join(context_parts)

    system = (
        "You are a careful research extractor. "
        "From the provided web content, extract only clear, concrete facts that help answer the research goal. "
        "Return a list of ExtractedFact objects. Each fact must include the source_urls it came from. "
        "Do not invent information. Prefer high-confidence claims."
    )

    human = f"Research goal: {goal}\n\nContent:\n{context}"

    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        structured = llm.with_structured_output(ExtractionResult)
        result: ExtractionResult = structured.invoke(
            [SystemMessage(content=system), HumanMessage(content=human)]
        )
        new_facts = result.facts or []
    except Exception as exc:
        errors.append(f"Extractor LLM call failed: {exc}")
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
