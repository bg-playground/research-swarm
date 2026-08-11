"""CLI entry point for research-swarm."""

from __future__ import annotations

import argparse
import json
import os
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-swarm",
        description=(
            "Multi-agent research system (LangGraph + Firecrawl). "
            "Give a research goal; get a cited markdown report from the live web."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main "Compare Firecrawl and Browserbase for LLM agents"
  research-swarm "Map open-source web data APIs for AI agents"
  python -m src.main --max-iterations 10 "Summarize Firecrawl docs for agent builders"

Environment:
  OPENAI_API_KEY      Required for supervisor / extractor / synthesizer
  FIRECRAWL_API_KEY   Required for live web discovery & scraping
  FIRECRAWL_API_URL   Optional (self-hosted Firecrawl)
  RESEARCH_SWARM_LOG_LEVEL  Optional (DEBUG/INFO/WARNING)
  LANGCHAIN_TRACING_V2      Optional (true to enable LangSmith)
        """,
    )
    parser.add_argument(
        "goal",
        nargs="*",
        help="Research goal (free text). If omitted, a default example goal is used.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=8,
        metavar="N",
        help="Max supervisor iterations (default: 8)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also print the structured_report JSON after the markdown report",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check environment / keys and exit (no research run)",
    )
    return parser


def _preflight() -> list[str]:
    """
    Return a list of human-readable warnings / problems.
    Does not raise — caller decides whether to continue.
    """
    issues: list[str] = []

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY", "").strip()

    if not openai_key or openai_key.startswith("sk-..."):
        issues.append(
            "OPENAI_API_KEY is missing or still a placeholder. "
            "Supervisor, extractor, and synthesizer need a real key."
        )
    if not firecrawl_key or firecrawl_key.startswith("fc-..."):
        issues.append(
            "FIRECRAWL_API_KEY is missing or still a placeholder. "
            "Discovery and gatherer will soft-fail without live web access."
        )

    return issues


def main(argv: list[str] | None = None) -> int:
    # Ensure .env is loaded before preflight
    try:
        from src import config  # noqa: F401  (loads dotenv on import)
    except Exception:
        pass

    from src.utils.logging_setup import enable_langsmith_if_configured, get_logger, setup_logging

    setup_logging()
    enable_langsmith_if_configured()
    log = get_logger("research_swarm.cli")

    parser = _build_parser()
    args = parser.parse_args(argv)

    issues = _preflight()

    if args.check:
        if issues:
            print("Environment check — issues found:\n")
            for i, msg in enumerate(issues, 1):
                print(f"  {i}. {msg}")
            print("\nCopy .env.example → .env and fill in real keys.")
            return 1
        print("Environment check — OK (OPENAI_API_KEY and FIRECRAWL_API_KEY look set).")
        return 0

    if issues:
        print("⚠️  Configuration warnings:\n")
        for msg in issues:
            print(f"  • {msg}")
        print("\nContinuing anyway — agents will soft-fail where keys are missing.\n")

    goal = " ".join(args.goal).strip()
    if not goal:
        goal = "Compare pricing and key features of leading web scraping APIs for AI agents"
        print("(No goal provided — using default example.)\n")

    print("🐝 research-swarm")
    print(f"Goal: {goal}")
    print(f"Max iterations: {args.max_iterations}")
    print("-" * 60)
    log.info("Starting research run goal=%r max_iterations=%s", goal, args.max_iterations)

    try:
        from src.graph import run_research
    except ImportError as exc:
        print(f"\nFailed to import research-swarm graph: {exc}")
        print("Try: pip install -e .")
        return 1

    try:
        final_state = run_research(goal, max_iterations=args.max_iterations)
    except KeyboardInterrupt:
        log.warning("Run interrupted by user")
        print("\nInterrupted.")
        return 130
    except Exception as exc:
        log.exception("Run failed")
        print(f"\nRun failed: {exc}")
        return 1

    log.info(
        "Run finished status=%s iterations=%s sources=%s facts=%s conflicts=%s",
        final_state.get("status"),
        final_state.get("iteration"),
        len(final_state.get("sources", [])),
        len(final_state.get("extracted_facts", [])),
        len(final_state.get("conflicts", [])),
    )

    print("\n--- Final Status ---")
    print(f"Status     : {final_state.get('status')}")
    print(f"Iterations : {final_state.get('iteration')}")
    print(f"Sources    : {len(final_state.get('sources', []))}")
    print(f"Facts      : {len(final_state.get('extracted_facts', []))}")
    print(f"Conflicts  : {len(final_state.get('conflicts', []))}")

    errors = final_state.get("errors") or []
    if errors:
        print(f"Errors     : {len(errors)} (last: {errors[-1][:120]})")

    report = final_state.get("report")
    if report:
        print("\n--- Report ---")
        print(report)
    else:
        print("\n(No report produced — check errors / keys / iterations.)")

    if args.json:
        structured = final_state.get("structured_report")
        if structured:
            print("\n--- Structured summary ---")
            print(json.dumps(structured, indent=2))

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
