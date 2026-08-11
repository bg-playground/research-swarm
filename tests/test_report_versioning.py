"""Tests for report versioning strategies and index resilience."""

from src.utils.report_versioning import (
    load_report_index,
    resolve_report_path,
    resolve_strategy,
    slugify_goal,
    update_report_index,
)


def test_resolve_strategy_defaults(monkeypatch):
    monkeypatch.delenv("RESEARCH_SWARM_REPORT_VERSIONING", raising=False)
    assert resolve_strategy(None) == "timestamp"
    assert resolve_strategy("sequential") == "sequential"
    assert resolve_strategy("bogus") == "timestamp"


def test_timestamp_paths_unique(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_SWARM_REPORTS_DIR", str(tmp_path))
    a = resolve_report_path("Firecrawl scrape API", strategy="timestamp")
    assert a.parent == tmp_path
    assert a.suffix == ".md"
    assert "firecrawl" in a.name


def test_sequential_increments(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_SWARM_REPORTS_DIR", str(tmp_path))
    p1 = resolve_report_path("Same goal", strategy="sequential")
    p1.parent.mkdir(parents=True, exist_ok=True)
    p1.write_text("v1", encoding="utf-8")
    p2 = resolve_report_path("Same goal", strategy="sequential")
    assert p1.name == "v001.md"
    assert p2.name == "v002.md"
    assert p1.parent == p2.parent


def test_latest_archives_on_change(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_SWARM_REPORTS_DIR", str(tmp_path))
    slug = slugify_goal("Latest strategy goal")
    latest = tmp_path / f"{slug}.md"
    latest.write_text("<!-- hdr -->\n\nold body", encoding="utf-8")

    path = resolve_report_path(
        "Latest strategy goal",
        strategy="latest",
        report_body="new body different",
    )
    assert path == latest
    archived = list((tmp_path / slug).glob("v*.md"))
    assert len(archived) == 1
    assert "old body" in archived[0].read_text(encoding="utf-8")


def test_latest_same_content_no_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_SWARM_REPORTS_DIR", str(tmp_path))
    slug = slugify_goal("Stable goal")
    latest = tmp_path / f"{slug}.md"
    latest.write_text("<!-- hdr -->\n\nsame body", encoding="utf-8")

    path = resolve_report_path(
        "Stable goal",
        strategy="latest",
        report_body="same body",
    )
    assert path == latest
    assert not (tmp_path / slug).exists() or not list((tmp_path / slug).glob("v*.md"))


def test_update_report_index(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_SWARM_REPORTS_DIR", str(tmp_path))
    report = tmp_path / "run.md"
    report.write_text("# x", encoding="utf-8")
    idx = update_report_index(
        path=report,
        goal="g",
        status="completed",
        n_src=1,
        n_facts=2,
        n_conf=0,
        n_iter=3,
        strategy="timestamp",
        fingerprint="abc",
    )
    assert idx is not None
    assert idx.is_file()
    data = idx.read_text(encoding="utf-8")
    assert "runs" in data
    assert "abc" in data


def test_load_report_index_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_SWARM_REPORTS_DIR", str(tmp_path))
    data = load_report_index()
    assert data["missing"] is True
    assert data["runs"] == []
    assert data["count"] == 0


def test_load_report_index_corrupt_then_update(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_SWARM_REPORTS_DIR", str(tmp_path))
    bad = tmp_path / "index.json"
    bad.write_text("{not-json", encoding="utf-8")

    loaded = load_report_index(bad)
    assert loaded.get("corrupt") is True

    report = tmp_path / "run.md"
    report.write_text("# ok", encoding="utf-8")
    idx = update_report_index(
        path=report,
        goal="recover",
        status="completed",
        n_src=0,
        n_facts=0,
        n_conf=0,
        n_iter=1,
        strategy="timestamp",
    )
    assert idx is not None
    assert idx.is_file()
    assert "recover" in idx.read_text(encoding="utf-8")
    assert (tmp_path / "index.json.bak").is_file()
