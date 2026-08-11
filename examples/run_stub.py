"""Example: run the research-swarm graph in pure stub mode (no API keys required for the stubs themselves)."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from the examples/ directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.graph import run_research


if __name__ == "__main__":
    goal = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "What are the main differences between Firecrawl and traditional web scrapers for LLM applications?"
    )

    print(f"Running stub research for:\n  {goal}\n")
    result = run_research(goal, max_iterations=6)

    print("=== Final report ===")
    print(result.get("report") or "(no report produced)")
    print("\n=== Key counts ===")
    print(f"sources         : {len(result.get('sources', []))}")
    print(f"extracted_facts : {len(result.get('extracted_facts', []))}")
    print(f"conflicts       : {len(result.get('conflicts', []))}")
    print(f"status          : {result.get('status')}")
    print(f"iterations      : {result.get('iteration')}")
