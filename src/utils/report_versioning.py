"""Report path versioning strategies for auto-saved research outputs.

Strategies
----------
timestamp   - reports/YYYYMMDD-HHMMSS-<slug>.md  (default; never overwrites)
sequential  - reports/<slug>/v001.md, v002.md, ...  (per-goal history)
latest      - reports/<slug>.md always overwritten; prior copy kept as
              reports/<slug>/vNNN.md when content changes

Configure via RESEARCH_SWARM_REPORT_VERSIONING or CLI --report-version.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

Strategy = Literal["timestamp", "sequential", "latest"]
VALID_STRATEGIES: tuple[Strategy, ...] = ("timestamp", "sequential", "latest")


def slugify_goal(goal: str, max_len: int = 48) -> str:
    text = (goal or "research").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-") or "research"
    return text[:max_len].rstrip("-")


def reports_dir() -> Path:
    raw = (os.getenv("RESEARCH_SWARM_REPORTS_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.cwd() / "reports"


def resolve_strategy(cli_value: Optional[str] = None) -> Strategy:
    raw = (cli_value or os.getenv("RESEARCH_SWARM_REPORT_VERSIONING") or "timestamp").strip().lower()
    if raw not in VALID_STRATEGIES:
        return "timestamp"
    return raw  # type: ignore[return-value]


def _content_fingerprint(report: str) -> str:
    return hashlib.sha256(report.encode("utf-8")).hexdigest()[:12]


def _next_sequential_path(goal_dir: Path) -> Path:
    goal_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(goal_dir.glob("v*.md"))
    next_n = 1
    for p in existing:
        m = re.match(r"v(\d+)\.md$", p.name, re.I)
        if m:
            next_n = max(next_n, int(m.group(1)) + 1)
    return goal_dir / f"v{next_n:03d}.md"


def resolve_report_path(
    goal: str,
    *,
    strategy: Optional[str] = None,
    report_body: Optional[str] = None,
) -> Path:
    strat = resolve_strategy(strategy)
    root = reports_dir()
    root.mkdir(parents=True, exist_ok=True)
    slug = slugify_goal(goal)

    if strat == "timestamp":
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return root / f"{stamp}-{slug}.md"

    if strat == "sequential":
        return _next_sequential_path(root / slug)

    latest = root / f"{slug}.md"
    if report_body is not None and latest.is_file():
        try:
            old = latest.read_text(encoding="utf-8")
            old_body = re.sub(r"^<!--.*?-->\s*", "", old, count=1, flags=re.S).strip()
            new_body = report_body.strip()
            if old_body == new_body:
                return latest
            archive = _next_sequential_path(root / slug)
            archive.write_text(old, encoding="utf-8")
        except OSError:
            pass
    return latest


def _empty_index() -> dict[str, Any]:
    return {
        "updated_at": None,
        "count": 0,
        "runs": [],
        "missing": True,
    }


def load_report_index(index_path: Optional[Path] = None) -> dict[str, Any]:
    """Load reports/index.json safely. Missing/corrupt never raises."""
    path = index_path or (reports_dir() / "index.json")
    if not path.is_file():
        return _empty_index()

    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        out = _empty_index()
        out["missing"] = False
        out["corrupt"] = True
        out["error"] = "unreadable"
        return out

    if not raw:
        out = _empty_index()
        out["missing"] = False
        out["empty"] = True
        return out

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        out = _empty_index()
        out["missing"] = False
        out["corrupt"] = True
        out["error"] = f"invalid json: {exc}"
        return out

    if isinstance(data, list):
        runs = [e for e in data if isinstance(e, dict)]
        return {
            "updated_at": None,
            "count": len(runs),
            "runs": runs,
            "missing": False,
        }

    if isinstance(data, dict):
        runs = data.get("runs")
        if not isinstance(runs, list):
            runs = []
        runs = [e for e in runs if isinstance(e, dict)]
        return {
            "updated_at": data.get("updated_at"),
            "count": len(runs),
            "runs": runs,
            "missing": False,
        }

    out = _empty_index()
    out["missing"] = False
    out["corrupt"] = True
    out["error"] = "unexpected index shape"
    return out


def update_report_index(
    *,
    path: Path,
    goal: str,
    status: Optional[str],
    n_src: int,
    n_facts: int,
    n_conf: int,
    n_iter: Optional[int],
    strategy: Strategy,
    fingerprint: Optional[str] = None,
) -> Optional[Path]:
    """Append run to index.json. Returns path or None; never raises."""
    try:
        root = reports_dir()
        root.mkdir(parents=True, exist_ok=True)
        index_path = root / "index.json"

        loaded = load_report_index(index_path)
        entries: list[dict[str, Any]] = list(loaded.get("runs") or [])

        if loaded.get("corrupt") and index_path.is_file():
            bak = index_path.with_suffix(".json.bak")
            try:
                index_path.replace(bak)
            except OSError:
                try:
                    bak.write_text(
                        index_path.read_text(encoding="utf-8", errors="replace"),
                        encoding="utf-8",
                    )
                except OSError:
                    pass

        try:
            rel = str(path.resolve().relative_to(root.resolve()))
        except ValueError:
            rel = str(path)

        entry = {
            "path": rel,
            "goal": goal,
            "status": status,
            "iterations": n_iter,
            "sources": n_src,
            "facts": n_facts,
            "conflicts": n_conf,
            "strategy": strategy,
            "fingerprint": fingerprint,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        entries.append(entry)
        entries = entries[-200:]

        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(entries),
            "runs": entries,
        }
        index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return index_path
    except OSError:
        return None
    except Exception:
        return None
