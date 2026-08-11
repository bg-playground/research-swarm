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
            "Multi-agent research system (LangGraph + Firecrawl).\n"
            "Give a research goal and get a cited markdown report from the live web.\n"
            "Reports auto-save under ./reports/ (see --report-version, --list-reports)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run research (auto-saves under reports/)
  python -m src.main "Compare Firecrawl and Browserbase for LLM agents"
  python -m src.main "From docs.firecrawl.dev, summarize search, scrape, crawl, map"

  # Save location & versioning
  python -m src.main -o report.md "Summarize Firecrawl docs for agent builders"
  python -m src.main --report-version sequential "Same goal -> v001.md, v002.md, ..."
  python -m src.main --report-version latest "Overwrite <slug>.md; archive on change"
  python -m src.main --no-save "Terminal only (do not write a file)"

  # Inspect past runs
  python -m src.main --list-reports
  python -m src.main --list-reports --limit 5
  python -m src.main --list-reports --json

  # Utilities
  python -m src.main --check
  python -m src.main --max-iterations 10 --json -o out.md "Your goal"
  research-swarm --help

Environment:
  OPENAI_API_KEY                 Required (supervisor / extractor / synthesizer)
  FIRECRAWL_API_KEY              Required (live search, scrape, map)
  FIRECRAWL_API_URL              Optional self-hosted Firecrawl base URL
  RESEARCH_SWARM_REPORTS_DIR     Report directory (default: ./reports)
  RESEARCH_SWARM_REPORT_VERSIONING  timestamp | sequential | latest
  RESEARCH_SWARM_CACHE_TTL_HOURS Scrape cache TTL hours (default: 24)
  RESEARCH_SWARM_CACHE_DISABLED  Set 1 to disable disk URL cache
  RESEARCH_SWARM_MODEL           Chat model id (default: gpt-4o-mini)
  RESEARCH_SWARM_LOG_LEVEL       DEBUG | INFO | WARNING | ERROR
  LANGCHAIN_TRACING_V2           true + LANGCHAIN_API_KEY for LangSmith
  NO_COLOR                       Disable ANSI colors
        """,
    )
    parser.add_argument("goal", nargs="*", help="Research goal as free text.")
    parser.add_argument("--max-iterations", type=int, default=8, metavar="N", help="Maximum supervisor iterations (default: 8).")
    parser.add_argument("--json", action="store_true", help="Print structured JSON (also with --list-reports).")
    parser.add_argument("-o", "--output", metavar="PATH", help="Write markdown report to PATH.")
    parser.add_argument("--no-save", action="store_true", help="Skip writing a report file.")
    parser.add_argument("--report-version", choices=["timestamp", "sequential", "latest"], default=None, metavar="STRATEGY", help="timestamp | sequential | latest")
    parser.add_argument("--list-reports", action="store_true", help="List recent saved reports and exit.")
    parser.add_argument("--limit", type=int, default=20, metavar="N", help="With --list-reports, max entries (default: 20).")
    parser.add_argument("--check", action="store_true", help="Validate API keys and exit.")
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


def _write_report_files(*, path: str, report: str | None, structured: dict | None, goal: str, status: str | None, n_src: int, n_facts: int, n_conf: int, n_iter: int | None) -> list[str]:
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
        payload = {"goal": goal, "status": status, "iterations": n_iter, "sources": n_src, "facts": n_facts, "conflicts": n_conf, "structured_report": structured}
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(str(json_path.resolve()))
    return written


def _list_reports(*, limit: int = 20, as_json: bool = False) -> int:
    from src.utils.report_versioning import load_report_index, reports_dir
    root = reports_dir()
    index_path = root / "index.json"
    data = load_report_index(index_path)
    if data.get("missing"):
        _safe_print(f"{S.dim}No report index found at {index_path}{S.reset}")
        _safe_print(f"{S.dim}Run a research goal first (reports auto-save under {root}).{S.reset}")
        return 0
    if data.get("corrupt"):
        err = data.get("error") or "unknown"
        _safe_print(f"{S.yellow}Report index is corrupt:{S.reset} {err}")
        _safe_print(f"{S.dim}Path: {index_path}{S.reset}")
        bak = index_path.with_suffix(".json.bak")
        if bak.is_file():
            _safe_print(f"{S.dim}Backup: {bak}{S.reset}")
        return 1
    runs = list(reversed(list(data.get("runs") or [])))
    limit = max(1, int(limit or 20))
    shown = runs[:limit]
    if as_json:
        payload = {"reports_dir": str(root), "index": str(index_path), "updated_at": data.get("updated_at"), "total": data.get("count", len(runs)), "showing": len(shown), "runs": shown}
        _safe_print(json.dumps(payload, indent=2))
        return 0
    _safe_print(f"{S.bold}{S.cyan}research-swarm reports{S.reset}")
    _safe_print(S.rule("-"))
    _safe_print(f"  {S.dim}dir{S.reset}    {root}")
    _safe_print(f"  {S.dim}index{S.reset}  {index_path}")
    total = data.get("count", len(runs))
    _safe_print(f"  {S.dim}total{S.reset}  {total}  (showing {len(shown)})")
    if data.get("updated_at"):
        _safe_print(f"  {S.dim}updated{S.reset} {data.get('updated_at')}")
    _safe_print(S.rule("-"))
    if not shown:
        _safe_print(f"{S.dim}(index exists but has no runs yet){S.reset}")
        return 0
    for i, run in enumerate(shown, 1):
        goal = (run.get("goal") or "").strip() or "(no goal)"
        if len(goal) > 72:
            goal = goal[:69] + "..."
        path = run.get("path") or "?"
        status = run.get("status") or "?"
        strat = run.get("strategy") or "?"
        saved = run.get("saved_at") or ""
        fp = run.get("fingerprint") or ""
        stats = f"src={run.get('sources', '?')} facts={run.get('facts', '?')} iter={run.get('iterations', '?')}"
        status_color = S.green if status == "completed" else S.yellow
        _safe_print(f"{S.bold}{i:2d}.{S.reset} [{status_color}{status}{S.reset}] {goal}")
        _safe_print(f"    {S.dim}path{S.reset}  {path}")
        _safe_print(f"    {S.dim}meta{S.reset}  {strat}  |  {stats}" + (f"  |  fp={fp}" if fp else ""))
        if saved:
            _safe_print(f"    {S.dim}when{S.reset}  {saved}")
    _safe_print()
    return 0


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

    if args.list_reports:
        return _list_reports(limit=args.limit, as_json=args.json)

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

    def _on_phase(node: str, state: dict, banner: str) -> None:
        _safe_print(f"{S.dim}{banner}{S.reset}")

    try:
        final_state = run_research(
            goal,
            max_iterations=args.max_iterations,
            on_phase=_on_phase,
        )
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

    log.info("Run finished status=%s iterations=%s sources=%s facts=%s conflicts=%s", status, n_iter, n_src, n_facts, n_conf)

    status_color = S.green if status == "completed" else S.yellow
    _safe_print()
    _safe_print(S.rule("-"))
    _safe_print(f"  {status_color}[{status}]{S.reset}  |  {n_iter} iterations  |  {n_src} sources  |  {n_facts} facts  |  {n_conf} conflicts")
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
                    from src.utils.report_versioning import _content_fingerprint, resolve_strategy, update_report_index
                    strat = resolve_strategy(version_strategy)
                    fp = _content_fingerprint(report) if report else None
                    idx = update_report_index(path=Path(written[0]), goal=goal, status=status, n_src=n_src, n_facts=n_facts, n_conf=n_conf, n_iter=n_iter, strategy=strat, fingerprint=fp)
                    if idx is not None:
                        _safe_print(f"{S.dim}Index{S.reset}  {idx}")
                    else:
                        _safe_print(f"{S.dim}Index{S.reset}  (skipped - reports/index.json unavailable)")
                except Exception as exc:
                    _safe_print(f"{S.dim}Index{S.reset}  (skipped - {type(exc).__name__})")
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
