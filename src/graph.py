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
    """
    Construct and compile the research-swarm StateGraph.

    Topology (supervisor-centric):
        START → supervisor ⇄ {discovery, gatherer, extractor, verifier, synthesizer}
                          ↘ END (when supervisor returns FINISH)
    """
    builder = StateGraph(ResearchState)

    # Register nodes
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("discovery", discovery_node)
    builder.add_node("gatherer", gatherer_node)
    builder.add_node("extractor", extractor_node)
    builder.add_node("verifier", verifier_node)
    builder.add_node("synthesizer", synthesizer_node)

    # Entry point
    builder.add_edge(START, "supervisor")

    # Specialists always return control to the supervisor via Command(goto="supervisor").
    # The supervisor itself returns Command(goto=<specialist> | "__end__").
    # Because we use Command-based routing, we do not need classic conditional edges
    # from the supervisor. We only need to declare that specialists can go back.
    for specialist in ["discovery", "gatherer", "extractor", "verifier", "synthesizer"]:
        builder.add_edge(specialist, "supervisor")

    # Compile
    graph = builder.compile()
    return graph


def create_initial_state(
    goal: str,
    *,
    max_iterations: int = 12,
    extra_messages: Optional[list] = None,
) -> ResearchState:
    """Build a valid starting ResearchState for a new research run."""
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
        next_agent=None,
        iteration=0,
        max_iterations=max_iterations,
        report=None,
        structured_report=None,
        errors=[],
        status="running",
    )


def run_research(
    goal: str,
    *,
    max_iterations: int = 12,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convenience helper: build the graph, create initial state, and invoke.

    Returns the final state dict.
    """
    graph = build_graph()
    initial = create_initial_state(goal, max_iterations=max_iterations)
    result = graph.invoke(initial, config=config or {})
    return result
