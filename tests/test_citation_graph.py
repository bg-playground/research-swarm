"""Unit tests for citation graph Mermaid builder."""

from src.state import ExtractedFact, Source
from src.utils.citation_graph import build_mermaid_citation_graph


def test_build_mermaid_citation_graph():
    sources = [
        Source(url="https://docs.example.com/a", title="Docs A"),
        Source(url="https://docs.example.com/b", title="Docs B"),
    ]
    facts = [
        ExtractedFact(
            claim="API supports markdown",
            value="markdown",
            source_urls=["https://docs.example.com/a"],
            confidence=0.9,
            evidence="Returns markdown by default.",
        )
    ]
    graph = build_mermaid_citation_graph(sources, facts)
    assert "```mermaid" in graph
    assert "flowchart LR" in graph
    assert "API supports markdown" in graph or "markdown" in graph
    assert "S1" in graph and "F1" in graph
