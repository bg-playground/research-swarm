"""Tests for Firecrawl Map enrichment in discovery."""

from src.agents import discovery as disc
from src.state import Source
from src.utils.query_rewrite import map_roots_from_goal, primary_domain_from_goal


def test_map_roots_from_goal_prefers_docs():
    roots = map_roots_from_goal(
        "From docs.firecrawl.dev, summarize search, scrape, crawl, map"
    )
    assert roots
    assert any("docs.firecrawl.dev" in r for r in roots)
    assert all(r.startswith("https://") for r in roots)
    primary = primary_domain_from_goal("site:docs.firecrawl.dev scrape API")
    assert primary and "docs.firecrawl.dev" in primary


def test_map_roots_empty_without_domain():
    assert map_roots_from_goal("Compare general web scraping approaches") == []


def test_discovery_merges_map_results(monkeypatch):
    search_hits = [
        Source(
            url="https://docs.firecrawl.dev/api-reference/endpoint/scrape",
            title="Scrape",
        ),
        Source(url="https://www.firecrawl.dev/", title="Home"),
    ]
    map_hits = [
        Source(
            url="https://docs.firecrawl.dev/api-reference/endpoint/crawl",
            title="Crawl",
            source_type="map",
            metadata={"from_map": True},
        ),
        Source(
            url="https://docs.firecrawl.dev/api-reference/endpoint/scrape",
            title="Scrape dup",
            source_type="map",
        ),
        Source(
            url="https://docs.firecrawl.dev/api-reference/endpoint/map",
            title="Map",
            source_type="map",
        ),
    ]

    monkeypatch.setattr(disc, "search_web", lambda *a, **k: list(search_hits))
    monkeypatch.setattr(disc, "map_site", lambda *a, **k: list(map_hits))

    state = {
        "goal": "From docs.firecrawl.dev, summarize search, scrape, crawl, map",
        "sources": [],
        "errors": [],
        "messages": [],
    }
    cmd = disc.discovery_node(state)
    urls = [s.url for s in cmd.update["sources"]]
    assert "https://docs.firecrawl.dev/api-reference/endpoint/crawl" in urls
    assert "https://docs.firecrawl.dev/api-reference/endpoint/map" in urls
    assert urls.count("https://docs.firecrawl.dev/api-reference/endpoint/scrape") == 1
    assert "map" in cmd.update["messages"][0].content.lower()


def test_discovery_map_soft_fails(monkeypatch):
    monkeypatch.setattr(
        disc,
        "search_web",
        lambda *a, **k: [
            Source(url="https://docs.firecrawl.dev/scrape", title="Scrape"),
        ],
    )

    def _boom(*a, **k):
        raise RuntimeError("map unavailable")

    monkeypatch.setattr(disc, "map_site", _boom)

    state = {
        "goal": "From docs.firecrawl.dev summarize scrape",
        "sources": [],
        "errors": [],
        "messages": [],
    }
    cmd = disc.discovery_node(state)
    assert any("map failed" in e.lower() for e in cmd.update.get("errors", []))
    assert len(cmd.update["sources"]) >= 1
