"""Verifier agent – cross-checks facts and scores source quality."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.types import Command

from src.state import Conflict, ResearchState, Source


def verifier_node(state: ResearchState) -> Command[Literal["supervisor"]]:
    """
    Verifier specialist.

    Performs lightweight quality scoring and conflict detection.
    A fuller LLM-as-judge version can be added later.
    """
    sources = list(state.get("sources", []))
    facts = state.get("extracted_facts", [])
    existing_conflicts = list(state.get("conflicts", []))
    errors = list(state.get("errors", []))

    if len(sources) == 0 and len(facts) == 0:
        return Command(
            goto="supervisor",
            update={
                "messages": [
                    AIMessage(content="Verifier: nothing to verify yet. Returning control.")
                ]
            },
        )

    # Simple heuristic quality adjustment
    updated_sources: list[Source] = []
    for src in sources:
        score = src.quality_score
        if src.markdown and len(src.markdown) > 500:
            score = min(score + 0.1, 0.95)
        if src.source_type == "scrape":
            score = min(score + 0.05, 0.98)
        updated_sources.append(src.model_copy(update={"quality_score": score}))

    new_conflicts = list(existing_conflicts)

    # Very lightweight conflict signal: multiple facts with the same claim but different values
    claim_map: dict[str, list] = {}
    for f in facts:
        key = f.claim.strip().lower()[:80]
        claim_map.setdefault(key, []).append(f)

    for claim, group in claim_map.items():
        if len(group) < 2:
            continue
        values = {str(g.value) for g in group}
        if len(values) > 1 and not any(c.description.startswith("Possible disagreement") for c in new_conflicts):
            new_conflicts.append(
                Conflict(
                    description=f"Possible disagreement on claim: '{group[0].claim[:60]}…'",
                    related_facts=[g.claim for g in group],
                    severity="low",
                )
            )

    updates = {
        "sources": updated_sources,
        "conflicts": new_conflicts,
        "messages": [
            AIMessage(
                content=(
                    f"Verifier: reviewed {len(sources)} source(s) and {len(facts)} fact(s). "
                    f"Conflicts: {len(new_conflicts)}."
                )
            )
        ],
        "errors": errors,
    }

    return Command(goto="supervisor", update=updates)
