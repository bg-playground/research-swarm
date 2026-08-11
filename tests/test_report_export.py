"""Tests for CLI report export helper."""

from src.main import _write_report_files


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
