"""Tests for phase progress banner."""

from src.graph import format_phase_banner
from src.state import Source


def test_format_phase_banner_basic():
    state = {
        "iteration": 3,
        "max_iterations": 8,
        "sources": [
            Source(url="https://a.example/1", title="A", markdown="# hi"),
            Source(url="https://a.example/2", title="B"),
        ],
        "extracted_facts": [{"claim": "x"}],
        "conflicts": [],
        "status": "running",
        "next_agent": "gatherer",
    }
    line = format_phase_banner("gatherer", state)
    assert "[3/8]" in line
    assert "gatherer" in line
    assert "2 sources" in line
    assert "1 scraped" in line
    assert "1 facts" in line


def test_format_phase_banner_supervisor_routes():
    state = {
        "iteration": 1,
        "max_iterations": 8,
        "sources": [],
        "extracted_facts": [],
        "conflicts": [],
        "next_agent": "discovery",
        "status": "running",
    }
    line = format_phase_banner("supervisor", state)
    assert "supervisor" in line
    assert "discovery" in line


def test_format_phase_banner_includes_conflicts():
    state = {
        "iteration": 5,
        "max_iterations": 8,
        "sources": [],
        "extracted_facts": [],
        "conflicts": [{"a": 1}, {"b": 2}],
        "status": "running",
    }
    line = format_phase_banner("verifier", state)
    assert "2 conflicts" in line
