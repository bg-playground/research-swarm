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

    def rule(self, char: str = "-", width: int = 56) -> str:
        safe = char if all(ord(c) < 128 for c in char) else "-"
        return f"{self.dim}{safe * width}{self.reset}"


S = _Style()


def _safe_print(text: str = "") -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


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
  python -m src.main -o report.md "Summarize Firecrawl docs for agent builders"
  python -m src.main --no-save "Quick run without writing a file"
  python -m src.main --report-version sequential "Re-run same goal with v001, v002..."
  python -m src.main --max-iterations 10 --json -o out.md "Your goal"

Environment:
  OPENAI_API_KEY      Required for supervisor / extractor / synthesizer
  FIRECRAWL_API_KEY   Required for live web discovery & scraping
  FIRECRAWL_API_URL   Optional (self-hosted Firecrawl)
  RESEARCH_SWARM_REPORTS_DIR  Optional (default: ./reports)
  RESEARCH_SWARM_REPORT_VERSIONING  timestamp|sequential|latest (default: timestamp)
  RESEARCH_SWARM_LOG_LEVEL  Optional (DEBUG/INFO/WARNING)
  LANGCHAIN_TRACING_V2      Optional (true to enable LangSmith)
  NO_COLOR                  Disable ANSI colors
        """,
    )
    parser.add_argument("goal", nargs="*", help="Research goal (free text).")
    parser.add_argument("--max-iterations", type=int, default=8, metavar="N")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-o", "--output", metavar="PATH", help="Explicit report path (overrides auto versioning).")
    parser.add_argument("--no-save", action="store_true", help="Do not write a report file.")
    parser.add_argument(
        "--report-version",
        choices=["timestamp", "sequential", "latest"],
        default=None,
        metavar="STRATEGY",
        help="timestamp (default) | sequential | latest",
    )
    parser.add_argument("--check", action="store_true")
    return parser


def _slugify_goal(goal: str, max_len: int = 48) -> str:
    from src.utils.report_versioning import slugify_goal

    return slugify_goal(goal, max_len=max_len)


def _reports_dir():
    from src.utils.report_versioning import reports_dir

    return reports_dir()


def _default_report_path(goal: str, *, strategy: str | None = None, report: str | None = None) -> str:
    from src.utils.report_versioning import resolve_report_path

    return str(resolve_report_path(goal, strategy=strategy, report_body=report))


def _write_report_files(
    *,
    path: str,
    report: str | None,
    structured: dict | None,
    goal: str,
    status: str | None,
    n_src: int,
    n_facts: int,
    n_conf: int,
    n_iter: int | None,
) -> list[str]:
    from pathlib import Path

    written: list[str] = []
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    if report:
        header = (
            f"<!-- research-swarm export\n"
            f"goal: {goal}\n"
            f"status: {status}\n"
            f"iterations: {n_iter}\n"
            f"sources: {n_src} | facts: {n_facts} | conflicts: {n_conf}\n"
            f"path: {out.name}\n"
            f"-->\n\n"
        )
        out.write_text(header + report, encoding="utf-8")
        written.append(str(out.resolve()))

    if structured is not None:
        json_path = out.with_suffix(".json") if out.suffix.lower() in {".md", ".markdown", ".txt"} else Path(str(out) + ".json")
        payload = {
            "goal": goal,
            "status": status,
            "iterations": n_iter,
            "sources": n_src,
            "facts": n_facts,
            "conflicts": n_conf,
            "structured_report": structured,
        }
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(str(json_path.resolve()))

    return written


def _preflight() -> list[str]:
    issues: list[str] = []
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not openai_key or openai_key.startswith("sk-..."):
        issues.append("OPENAI_API_KEY is missing or still a placeholder.")
    if not firecrawl_key or firecrawl_key.startswith("fc-..."):
        issues.append("FIRECRAWL_API_KEY is missing or still a placeholder.")
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
            _safe_print(f"{S.yellow}Environment check - issues found:{S.reset}\n")
            for i, msg in enumerate(issues, 1):
                _safe_print(f"  {i}. {msg}")
            return 1
        _safe_print(f"{S.green}Environment check - OK{S.reset}")
        return 0

    if issues:
        _safe_print(f"{S.yellow}! Configuration warnings:{S.reset}\n")
        for msg in issues:
            _safe_print(f"  * {msg}")
        _safe_print(f"\n{S.dim}Continuing anyway.{S.reset}\n")

    goal = " ".join(args.goal).strip()
    if not goal:
        goal = "Compare pricing and key features of leading web scraping APIs for AI agents"
        _safe_print(f"{S.dim}(No goal provided - using default example.){S.reset}\n")

    _safe_print()
    _safe_print(f"{S.bold}{S.cyan}research-swarm{S.reset}")
    _safe_print(S.rule("="))
    _safe_print(f"  {S.dim}Goal{S.reset}            {goal}")
    _safe_print(f"  {S.dim}Max iterations{S.reset}  {args.max_iterations}")
    _safe_print(S.rule("="))
    _safe_print()
    log.info("Starting research run goal=%r max_iterations=%s", goal, args.max_iterations)

    try:
        from src.graph import run_research
    except ImportError as exc:
        _safe_print(f"\n{S.red}Failed to import graph:{S.reset} {exc}")
        return 1

    try:
        final_state = run_research(goal, max_iterations=args.max_iterations)
    except KeyboardInterrupt:
        _safe_print(f"\n{S.yellow}Interrupted.{S.reset}")
        return 130
    except Exception as exc:
        log.exception("Run failed")
        _safe_print(f"\n{S.red}Run failed:{S.reset} {exc}")
        return 1

    status = final_state.get("status")
    n_src = len(final_state.get("sources", []))
    n_facts = len(final_state.get("extracted_facts", []))
    n_conf = len(final_state.get("conflicts", []))
    n_iter = final_state.get("iteration")

    log.info(
        "Run finished status=%s iterations=%s sources=%s facts=%s conflicts=%s",
        status, n_iter, n_src, n_facts, n_conf,
    )

    status_color = S.green if status == "completed" else S.yellow
    _safe_print()
    _safe_print(S.rule("-"))
    _safe_print(
        f"  {status_color}[{status}]{S.reset}  |  {n_iter} iterations  |  "
        f"{n_src} sources  |  {n_facts} facts  |  {n_conf} conflicts"
    )
    _safe_print(S.rule("-"))

    errors = final_state.get("errors") or []
    if errors:
        _safe_print(f"\n{S.yellow}Errors ({len(errors)}){S.reset}  last: {errors[-1][:120]}")

    report = final_state.get("report")
    if report:
        _safe_print()
        _safe_print(f"{S.bold}{S.cyan}Report{S.reset}")
        _safe_print(S.rule("="))
        _safe_print(report)
        _safe_print(S.rule("="))
    else:
        _safe_print(f"\n{S.dim}(No report produced.){S.reset}")

    output_path: str | None = None
    version_strategy = getattr(args, "report_version", None)
    if args.output:
        output_path = args.output
    elif not args.no_save:
        output_path = _default_report_path(goal, strategy=version_strategy, report=report)

    if output_path:
        written = _write_report_files(
            path=output_path,
            report=report,
            structured=final_state.get("structured_report") if args.json else None,
            goal=goal,
            status=status,
            n_src=n_src,
            n_facts=n_facts,
            n_conf=n_conf,
            n_iter=n_iter,
        )
        if written:
            for p in written:
                _safe_print(f"{S.green}Wrote{S.reset} {p}")
            if not args.output:
                try:
                    from pathlib import Path
                    from src.utils.report_versioning import (
                        _content_fingerprint,
                        resolve_strategy,
                        update_report_index,
                    )

                    strat = resolve_strategy(version_strategy)
                    fp = _content_fingerprint(report) if report else None
                    idx = update_report_index(
                        path=Path(written[0]),
                        goal=goal,
                        status=status,
                        n_src=n_src,
                        n_facts=n_facts,
                        n_conf=n_conf,
                        n_iter=n_iter,
                        strategy=strat,
                        fingerprint=fp,
                    )
                    _safe_print(f"{S.dim}Index{S.reset}  {idx}")
                except Exception:
                    pass
        else:
            _safe_print(f"{S.yellow}No report content to write to {output_path}{S.reset}")

    if args.json:
        structured = final_state.get("structured_report")
        if structured:
            _safe_print(f"\n{S.dim}Structured summary{S.reset}")
            _safe_print(json.dumps(structured, indent=2))

    _safe_print(f"\n{S.dim}Done.{S.reset}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
