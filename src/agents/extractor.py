"""Extractor agent stub – pulls structured facts from collected content."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.types import Command

from src.state import ExtractedFact, ResearchState


def extractor_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """
    Extractor specialist (stub).

    In the real implementation this will use Firecrawl's extract / agent endpoint
    (or an LLM with the clean markdown) to produce typed ExtractedFact objects.
    """
    sources = state.get("sources", [])
    existing_facts = list(state.get("extracted_facts", []))
    goal = state.get("goal", "unknown")

    # Only consider sources that actually have content
    contentful = [s for s in sources if s.markdown]

    if not contentful:
        return Command(
            goto="supervisor",
            update={
                "messages": [
                    AIMessage(
                        content="Extractor (stub): no sources with markdown content. Skipping."
                    )
                ]
            },
        )

    # TODO: Replace with real structured extraction
    # Prefer Firecrawl extract with a JSON schema derived from the goal,
    # or an LLM call over the markdown.

    new_facts = [
        ExtractedFact(
            claim=f"Key point related to '{goal[:50]}'",
            value="Placeholder value – replace with real extraction",
            source_urls=[contentful[0].url],
            confidence=0.65,
            category="general",
        ),
        ExtractedFact(
            claim="Secondary observation (stub)",
            value={"note": "This would be structured data from the page"},
            source_urls=[s.url for s in contentful[:2]],
            confidence=0.55,
            category="metadata",
        ),
    ]

    updates = {
        "extracted_facts": existing_facts + new_facts,
        "messages": [
            AIMessage(
                content=f"Extractor (stub): produced {len(new_facts)} placeholder fact(s) "
                f"from {len(contentful)} source(s)."
            )
        ],
    }

    return Command(goto="supervisor", update=updates)
