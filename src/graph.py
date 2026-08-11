"""LangGraph wiring for the research-swarm multi-agent system."""

from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from src.agents import (
    discovery_node,
    extractor_node,
    gatherer_node,
    supervisor_node,
    synthesizer_node,
    verifier_node,
)
from src.state import ResearchPlan, ResearchState


def build_graph():
    """Construct and compile the research-swarm StateGraph."""
    builder = StateGraph(ResearchState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("discovery", discovery_node)
    builder.add_node("gatherer", gatherer_node)
    builder.add_node("extractor", extractor_node)
    builder.add_node("verifier", verifier_node)
    builder.add_node("synthesizer", synthesizer_node)

    builder.add_edge(START, "supervisor")

    for specialist in ["discovery", "gatherer", "extractor", "verifier", "synthesizer"]:
        builder.add_edge(specialist, "supervisor")

    return builder.compile()


def create_initial_state(
    goal: str,
    *,
    max_iterations: int = 12,
    extra_messages: Optional[list] = None,
) -> ResearchState:
    messages = [HumanMessage(content=f"Research goal: {goal}")]
    if extra_messages:
        messages.extend(extra_messages)

    return ResearchState(
        messages=messages,
        goal=goal,
        plan=ResearchPlan(goal=goal, subtasks=[], completed_subtasks=[]),
        sources=[],
        extracted_facts=[],
        conflicts=[],
        extracted_urls=[],
        next_agent=None,
        iteration=0,
        max_iterations=max_iterations,
        report=None,
        structured_report=None,
        errors=[],
        status="running",
    )


def _count_scraped(sources: list) -> int:
    n = 0
    for s in sources or []:
        md = getattr(s, "markdown", None)
        if md is None and isinstance(s, dict):
            md = s.get("markdown")
        if md:
            n += 1
    return n


def format_phase_banner(
    node: str,
    state: Dict[str, Any],
    *,
    max_iterations: int | None = None,
) -> str:
    """One-line progress banner after a graph node completes."""
    it = state.get("iteration") or 0
    max_i = state.get("max_iterations") or max_iterations or 12
    sources = state.get("sources") or []
    facts = state.get("extracted_facts") or []
    conflicts = state.get("conflicts") or []
    scraped = _count_scraped(sources)
    status = state.get("status") or "running"
    next_agent = state.get("next_agent")

    label = node
    if node == "supervisor" and next_agent:
        label = f"supervisor -> {next_agent}"

    parts = [
        f"[{it}/{max_i}]",
        label,
        f"{len(sources)} sources",
        f"{scraped} scraped",
        f"{len(facts)} facts",
    ]
    if conflicts:
        parts.append(f"{len(conflicts)} conflicts")
    if status and status != "running" and node in ("synthesizer", "supervisor"):
        parts.append(str(status))
    return " · ".join(parts)


def run_research(
    goal: str,
    *,
    max_iterations: int = 12,
    config: Optional[Dict[str, Any]] = None,
    on_phase: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Build the graph and run research.

    When ``on_phase`` is provided it is called as
    ``on_phase(node_name, state_dict, banner_line)`` after each node.
    """
    graph = build_graph()
    initial = create_initial_state(goal, max_iterations=max_iterations)
    cfg = config or {}

    if on_phase is None:
        return graph.invoke(initial, config=cfg)

    snapshot: Dict[str, Any] = dict(initial)
    final: Dict[str, Any] = snapshot

    for update in graph.stream(initial, config=cfg, stream_mode="updates"):
        if not isinstance(update, dict):
            continue
        for node_name, node_payload in update.items():
            if isinstance(node_payload, dict):
                snapshot = {**snapshot, **node_payload}
            final = snapshot
            banner = format_phase_banner(
                str(node_name), snapshot, max_iterations=max_iterations
            )
            try:
                on_phase(str(node_name), snapshot, banner)
            except Exception:
                pass

    return final
