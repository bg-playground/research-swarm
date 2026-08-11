"""Tests for CLI report export helper."""

from src.main import _default_report_path, _slugify_goal, _write_report_files


def test_write_report_files(tmp_path):
    md = tmp_path / "out" / "report.md"
    paths = _write_report_files(
        path=str(md),
        report="# Hello\n\nBody",
        structured={"goal": "x", "num_sources": 1},
        goal="test goal",
        status="completed",
        n_src=1,
        n_facts=2,
        n_conf=0,
        n_iter=5,
    )
    assert md.is_file()
    text = md.read_text(encoding="utf-8")
    assert "research-swarm export" in text
    assert "# Hello" in text
    assert any(p.endswith(".json") for p in paths)


def test_slugify_goal():
    assert "firecrawl" in _slugify_goal("From docs.firecrawl.dev, summarize APIs!")
    assert _slugify_goal("@@@") == "research"


def test_default_report_path_under_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_SWARM_REPORTS_DIR", str(tmp_path / "my-reports"))
    path = _default_report_path("Summarize Firecrawl scrape API")
    assert "my-reports" in path.replace("\\", "/")
    assert path.endswith(".md")
