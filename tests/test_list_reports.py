"""Tests for --list-reports CLI helper and --help documentation."""

import json

from src.main import _build_parser, _list_reports


def test_list_reports_missing_index(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RESEARCH_SWARM_REPORTS_DIR", str(tmp_path))
    code = _list_reports(limit=5)
    assert code == 0
    out = capsys.readouterr().out
    assert "No report index" in out or "index" in out.lower()


def test_list_reports_shows_runs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RESEARCH_SWARM_REPORTS_DIR", str(tmp_path))
    index = {
        "updated_at": "2026-08-11T12:00:00+00:00",
        "count": 2,
        "runs": [
            {
                "path": "older.md",
                "goal": "Older goal about widgets",
                "status": "completed",
                "strategy": "timestamp",
                "sources": 3,
                "facts": 2,
                "iterations": 4,
                "fingerprint": "aaa",
                "saved_at": "2026-08-11T11:00:00+00:00",
            },
            {
                "path": "newer.md",
                "goal": "From docs.firecrawl.dev summarize APIs",
                "status": "completed",
                "strategy": "sequential",
                "sources": 8,
                "facts": 7,
                "iterations": 7,
                "fingerprint": "bbb",
                "saved_at": "2026-08-11T12:00:00+00:00",
            },
        ],
    }
    (tmp_path / "index.json").write_text(json.dumps(index), encoding="utf-8")
    code = _list_reports(limit=10)
    assert code == 0
    out = capsys.readouterr().out
    assert out.index("newer.md") < out.index("older.md")
    assert "docs.firecrawl.dev" in out
    assert "sequential" in out


def test_list_reports_json_mode(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RESEARCH_SWARM_REPORTS_DIR", str(tmp_path))
    (tmp_path / "index.json").write_text(
        json.dumps({"count": 1, "runs": [{"path": "a.md", "goal": "g", "status": "completed"}]}),
        encoding="utf-8",
    )
    code = _list_reports(limit=5, as_json=True)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["showing"] == 1
    assert payload["runs"][0]["path"] == "a.md"


def test_list_reports_corrupt_index(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RESEARCH_SWARM_REPORTS_DIR", str(tmp_path))
    (tmp_path / "index.json").write_text("{nope", encoding="utf-8")
    code = _list_reports(limit=5)
    assert code == 1
    out = capsys.readouterr().out
    assert "corrupt" in out.lower()


def test_help_documents_flags():
    help_text = _build_parser().format_help()
    for token in (
        "--list-reports",
        "--report-version",
        "--no-save",
        "--output",
        "--check",
        "--limit",
        "--json",
        "--max-iterations",
        "RESEARCH_SWARM_REPORTS_DIR",
        "FIRECRAWL_API_KEY",
        "timestamp",
        "sequential",
        "latest",
    ):
        assert token in help_text, f"missing from --help: {token}"
