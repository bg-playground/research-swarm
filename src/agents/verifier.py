"""Verifier agent stub – cross-checks facts and scores source quality."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.types import Command

from src.state import Conflict, ResearchState, Source


def verifier_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """
    Verifier specialist (stub).

    In the real implementation this agent will:
    - Compare facts across sources
    - Detect contradictions
    - Adjust quality_score on sources
    - Possibly request additional gathering if confidence is low
    """
    sources = list(state.get("sources", []))
    facts = state.get("extracted_facts", [])
    existing_conflicts = list(state.get("conflicts", []))

    if len(facts) < 2 and len(sources) < 2:
        return Command(
            goto="supervisor",
            update={
                "messages": [
                    AIMessage(
                        content="Verifier (stub): insufficient data to verify. Returning control."
                    )
                ]
            },
        )

    # TODO: Real verification logic
    # - Embeddings or LLM-as-judge to find contradictions
    # - Source reputation heuristics
    # - Confidence recalibration

    # Stub behaviour: mildly boost quality scores and occasionally invent a low-severity conflict
    updated_sources: list[Source] = []
    for src in sources:
        new_score = min(src.quality_score + 0.05, 0.98)
        updated_sources.append(src.model_copy(update={"quality_score": new_score}))

    new_conflicts = list(existing_conflicts)
    if len(facts) >= 2 and len(existing_conflicts) == 0:
        # Add one illustrative conflict so downstream code has something to work with
        new_conflicts.append(
            Conflict(
                description="Stub conflict: two sources appear to disagree on a detail "
                "(replace with real cross-checking).",
                related_facts=[f.claim for f in facts[:2]],
                severity="low",
            )
        )

    updates = {
        "sources": updated_sources,
        "conflicts": new_conflicts,
        "messages": [
            AIMessage(
                content=(
                    f"Verifier (stub): reviewed {len(sources)} source(s) and "
                    f"{len(facts)} fact(s). "
                    f"Conflicts now: {len(new_conflicts)}."
                )
            )
        ],
    }

    return Command(goto="supervisor", update=updates)
