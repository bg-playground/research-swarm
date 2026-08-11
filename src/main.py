"""CLI entry point for research-swarm."""

from __future__ import annotations

import argparse
import json
import os
import sys


def _use_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty()


class _Style:
    def __init__(self) -> None:
        on = _use_color()
        self.bold = "\033[1m" if on else ""
        self.dim = "\033[2m" if on else ""
        self.cyan = "\033[36m" if on else ""
        self.green = "\033[32m" if on else ""
        self.yellow = "\033[33m" if on else ""
        self.red = "\033[31m" if on else ""
        self.reset = "\033[0m" if on else ""

    def rule(self, char: str = "\u2500", width: int = 56) -> str:
        return f"{self.dim}{char * width}{self.reset}"


S = _Style()


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
  NO_COLOR                  Disable ANSI colors
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
    try:
        from src import config  # noqa: F401
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
            print(f"{S.yellow}Environment check \u2014 issues found:{S.reset}\n")
            for i, msg in enumerate(issues, 1):
                print(f"  {i}. {msg}")
            print(f"\n{S.dim}Copy .env.example \u2192 .env and fill in real keys.{S.reset}")
            return 1
        print(f"{S.green}Environment check \u2014 OK{S.reset} (OPENAI_API_KEY and FIRECRAWL_API_KEY look set).")
        return 0

    if issues:
        print(f"{S.yellow}\u26a0  Configuration warnings:{S.reset}\n")
        for msg in issues:
            print(f"  \u2022 {msg}")
        print(f"\n{S.dim}Continuing anyway \u2014 agents will soft-fail where keys are missing.{S.reset}\n")

    goal = " ".join(args.goal).strip()
    if not goal:
        goal = "Compare pricing and key features of leading web scraping APIs for AI agents"
        print(f"{S.dim}(No goal provided \u2014 using default example.){S.reset}\n")

    print()
    print(f"{S.bold}{S.cyan}\ud83d\udc1d  research-swarm{S.reset}")
    print(S.rule())
    print(f"  {S.dim}Goal{S.reset}            {goal}")
    print(f"  {S.dim}Max iterations{S.reset}  {args.max_iterations}")
    print(S.rule())
    print()
    log.info("Starting research run goal=%r max_iterations=%s", goal, args.max_iterations)

    try:
        from src.graph import run_research
    except ImportError as exc:
        print(f"\n{S.red}Failed to import research-swarm graph:{S.reset} {exc}")
        print(f"{S.dim}Try: pip install -e .{S.reset}")
        return 1

    try:
        final_state = run_research(goal, max_iterations=args.max_iterations)
    except KeyboardInterrupt:
        log.warning("Run interrupted by user")
        print(f"\n{S.yellow}Interrupted.{S.reset}")
        return 130
    except Exception as exc:
        log.exception("Run failed")
        print(f"\n{S.red}Run failed:{S.reset} {exc}")
        return 1

    status = final_state.get("status")
    n_src = len(final_state.get("sources", []))
    n_facts = len(final_state.get("extracted_facts", []))
    n_conf = len(final_state.get("conflicts", []))
    n_iter = final_state.get("iteration")

    log.info(
        "Run finished status=%s iterations=%s sources=%s facts=%s conflicts=%s",
        status,
        n_iter,
        n_src,
        n_facts,
        n_conf,
    )

    status_color = S.green if status == "completed" else S.yellow
    print()
    print(S.rule())
    print(
        f"  {status_color}\u2713 {status}{S.reset}  \u00b7  {n_iter} iterations  \u00b7  "
        f"{n_src} sources  \u00b7  {n_facts} facts  \u00b7  {n_conf} conflicts"
    )
    print(S.rule())

    errors = final_state.get("errors") or []
    if errors:
        print(f"\n{S.yellow}Errors ({len(errors)}){S.reset}  last: {errors[-1][:120]}")

    report = final_state.get("report")
    if report:
        print()
        print(f"{S.bold}{S.cyan}\ud83d\udcc4  Report{S.reset}")
        print(S.rule("\u2550"))
        print(report)
        print(S.rule("\u2550"))
    else:
        print(f"\n{S.dim}(No report produced \u2014 check errors / keys / iterations.){S.reset}")

    if args.json:
        structured = final_state.get("structured_report")
        if structured:
            print(f"\n{S.dim}Structured summary{S.reset}")
            print(json.dumps(structured, indent=2))

    print(f"\n{S.dim}Done.{S.reset}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
