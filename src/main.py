"""Minimal CLI entry point to exercise the research-swarm stubs."""

from __future__ import annotations

import json
import sys

from src.graph import run_research


def main() -> None:
    goal = " ".join(sys.argv[1:]).strip()
    if not goal:
        goal = "Compare pricing and key features of leading web scraping APIs for AI agents"

    print(f"\n🐝 research-swarm (stub mode)")
    print(f"Goal: {goal}\n")
    print("-" * 60)

    final_state = run_research(goal, max_iterations=8)

    print("\n--- Final Status ---")
    print(f"Status     : {final_state.get('status')}")
    print(f"Iterations : {final_state.get('iteration')}")
    print(f"Sources    : {len(final_state.get('sources', []))}")
    print(f"Facts      : {len(final_state.get('extracted_facts', []))}")
    print(f"Conflicts  : {len(final_state.get('conflicts', []))}")

    report = final_state.get("report")
    if report:
        print("\n--- Report (stub) ---")
        print(report)

    structured = final_state.get("structured_report")
    if structured:
        print("\n--- Structured summary ---")
        print(json.dumps(structured, indent=2))

    print("\nDone.\n")


if __name__ == "__main__":
    main()
