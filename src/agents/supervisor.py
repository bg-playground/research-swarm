"""Supervisor agent – plans and routes work to specialist agents."""

from __future__ import annotations

from typing import Literal, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from src.config import get_chat_model
from src.state import ResearchPlan, ResearchState
from src.utils.logging_setup import get_logger

log = get_logger("research_swarm.supervisor")


class SupervisorDecision(BaseModel):
    """Structured output the supervisor must produce."""

    reasoning: str = Field(
        description="Brief explanation of the current situation and why this decision was made."
    )
    next_agent: Literal[
        "discovery", "gatherer", "extractor", "verifier", "synthesizer", "FINISH"
    ] = Field(description="Which specialist should run next, or FINISH if research is complete.")
    updated_plan: Optional[ResearchPlan] = Field(
        default=None,
        description="Optional light re-plan. Only provide when subtasks need adjustment.",
    )
    status_note: Optional[str] = Field(
        default=None,
        description="Short status update for logging / human observation.",
    )


SUPERVISOR_SYSTEM_PROMPT = """You are the Supervisor of a multi-agent research swarm.

Your job is to examine the current research state and decide the single best next action.

Available specialists:
- discovery  → Search the web and map site structures (use early to find good sources)
- gatherer   → Scrape or crawl pages to obtain clean markdown content
- extractor  → Pull structured facts / JSON from collected content
- verifier   → Cross-check facts, detect conflicts, score source quality
- synthesizer → Write the final cited report
- FINISH     → Research is complete enough; stop the loop

Rules:
1. Prefer a logical sequence: discovery → gatherer → extractor → verifier → synthesizer.
2. You may jump ahead or go back if the state clearly requires it (e.g. missing sources → discovery).
3. Light re-planning is allowed: you may add, remove, or re-order subtasks when it clearly improves the research.
4. Never invent facts. Only route.
5. Coverage bias (important):
   - If "Sources not yet scraped" is >= 2 and iterations remain, prefer **gatherer** before synthesizer.
   - If "Sources pending extract" is >= 1, prefer **extractor** before verifier/synthesizer.
   - Do not FINISH early while high-quality unscored sources remain and budget allows another gather+extract cycle.
6. Stop (FINISH) when:
   - The original goal is adequately answered with solid coverage, or
   - max_iterations is approaching and we have usable results, or
   - Further work would add little value (few/no unscored sources left).
7. Keep reasoning concise (2-4 sentences).

Current research goal: {goal}
Current iteration: {iteration} / {max_iterations}
"""


def _build_supervisor_messages(state: ResearchState) -> list:
    goal = state.get("goal", "No goal provided")
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 12)

    system = SUPERVISOR_SYSTEM_PROMPT.format(
        goal=goal,
        iteration=iteration,
        max_iterations=max_iterations,
    )

    plan = state.get("plan")
    sources = state.get("sources", [])
    facts = state.get("extracted_facts", [])
    conflicts = state.get("conflicts", [])
    errors = state.get("errors", [])

    summary_parts = []
    if plan:
        summary_parts.append(f"Plan goal: {plan.goal}")
        summary_parts.append(f"Subtasks: {plan.subtasks}")
        summary_parts.append(f"Completed: {plan.completed_subtasks}")
        if plan.notes:
            summary_parts.append(f"Plan notes: {plan.notes}")

    already = set(state.get("extracted_urls") or [])
    contentful = [s for s in sources if s.markdown]
    pending_extract = [s for s in contentful if s.url not in already]
    unscored = [s for s in sources if not s.markdown]

    summary_parts.append(f"Sources collected: {len(sources)}")
    summary_parts.append(f"Sources with markdown: {len(contentful)}")
    summary_parts.append(f"Sources not yet scraped: {len(unscored)}")
    summary_parts.append(f"Sources pending extract: {len(pending_extract)}")
    summary_parts.append(f"Extracted facts: {len(facts)}")
    summary_parts.append(f"Conflicts detected: {len(conflicts)}")
    if errors:
        summary_parts.append(f"Recent errors: {errors[-3:]}")

    human_content = "Current state summary:\n" + "\n".join(f"- {p}" for p in summary_parts)
    recent_messages = state.get("messages", [])[-4:]

    messages = [SystemMessage(content=system), HumanMessage(content=human_content)]
    messages.extend(recent_messages)
    return messages


def _coverage_route(state: ResearchState) -> Optional[str]:
    """
    Prefer gatherer/extractor when coverage is incomplete and budget remains.

    Returns a specialist name, or None to fall through to the LLM.
    """
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 12)
    remaining = max_iterations - iteration
    if remaining <= 2:
        return None

    sources = state.get("sources", [])
    facts = state.get("extracted_facts", [])
    already = set(state.get("extracted_urls") or [])
    contentful = [s for s in sources if s.markdown]
    pending_extract = [s for s in contentful if s.url not in already]
    unscored = [s for s in sources if not s.markdown]

    if len(pending_extract) >= 1:
        return "extractor"

    if len(unscored) >= 2 and remaining >= 3 and len(facts) < 10:
        return "gatherer"

    return None


def supervisor_node(state: ResearchState) -> Command[Literal[
    "discovery", "gatherer", "extractor", "verifier", "synthesizer", "__end__"
]]:
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 12)

    if iteration >= max_iterations:
        log.info("Max iterations reached (%s) — finishing", max_iterations)
        return Command(
            goto="__end__",
            update={
                "next_agent": "FINISH",
                "status": "completed",
                "messages": [AIMessage(content="Max iterations reached. Stopping research.")],
            },
        )

    forced = _coverage_route(state)
    if forced:
        log.info(
            "iteration=%s next=%s sources=%s facts=%s | coverage heuristic",
            iteration + 1,
            forced,
            len(state.get("sources", [])),
            len(state.get("extracted_facts", [])),
        )
        return Command(
            goto=forced,
            update={
                "next_agent": forced,
                "iteration": iteration + 1,
                "messages": [
                    AIMessage(
                        content=(
                            f"Supervisor: coverage heuristic → {forced} "
                            "(unscored sources or pending extract remain)."
                        )
                    )
                ],
            },
        )

    llm = get_chat_model(temperature=0)
    structured_llm = llm.with_structured_output(SupervisorDecision, method="function_calling")

    messages = _build_supervisor_messages(state)
    decision: SupervisorDecision = structured_llm.invoke(messages)

    log.info(
        "iteration=%s next=%s sources=%s facts=%s | %s",
        iteration + 1,
        decision.next_agent,
        len(state.get("sources", [])),
        len(state.get("extracted_facts", [])),
        decision.reasoning[:120].replace("\n", " "),
    )

    updates: dict = {
        "next_agent": decision.next_agent,
        "iteration": iteration + 1,
        "messages": [
            AIMessage(
                content=f"Supervisor: {decision.reasoning}"
                + (f" | Note: {decision.status_note}" if decision.status_note else "")
            )
        ],
    }

    if decision.updated_plan is not None:
        updates["plan"] = decision.updated_plan

    if decision.next_agent == "FINISH":
        updates["status"] = "completed"
        return Command(goto="__end__", update=updates)

    return Command(goto=decision.next_agent, update=updates)
