"""Smoke tests that run without real API keys (Firecrawl + LLM mocked)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.state import ExtractedFact, ResearchPlan, ResearchState, Source
from src.utils.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


# ---------- State / models ----------

def test_source_model_defaults():
    s = Source(url="https://example.com")
    assert s.url == "https://example.com"
    assert s.quality_score == 0.5
    assert s.source_type == "scrape"


def test_research_plan():
    plan = ResearchPlan(goal="test goal", subtasks=["a", "b"])
    assert plan.goal == "test goal"
    assert len(plan.subtasks) == 2
    assert plan.completed_subtasks == []


# ---------- Circuit breaker ----------

def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0, name="test")
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True

    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_circuit_breaker_success_resets():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0, name="test")
    cb.record_failure()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb._failure_count == 0


def test_circuit_open_error_message():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=30.0, name="fc")
    cb.record_failure()
    err = CircuitOpenError(cb)
    assert "OPEN" in str(err)
    assert "fc" in str(err)


# ---------- Tools (mocked Firecrawl) ----------

def test_search_web_with_mock():
    mock_item = MagicMock()
    mock_item.url = "https://example.com/page"
    mock_item.title = "Example"
    mock_item.description = "A page"
    mock_item.markdown = None

    mock_result = MagicMock()
    mock_result.web = [mock_item]

    mock_client = MagicMock()
    mock_client.search.return_value = mock_result

    with patch("src.tools.firecrawl_tools.get_firecrawl_client", return_value=mock_client):
        from src.tools import firecrawl_tools as ft

        ft._firecrawl_breaker.record_success()
        sources = ft.search_web("test query", limit=3)

    assert len(sources) == 1
    assert sources[0].url == "https://example.com/page"
    assert sources[0].source_type == "search"
    mock_client.search.assert_called_once()


def test_scrape_url_with_mock():
    mock_doc = MagicMock()
    mock_doc.markdown = "# Hello\n\nWorld content here."
    mock_doc.title = "Hello Page"
    mock_doc.metadata = {"title": "Hello Page"}

    mock_client = MagicMock()
    mock_client.scrape.return_value = mock_doc

    with patch("src.tools.firecrawl_tools.get_firecrawl_client", return_value=mock_client):
        from src.tools import firecrawl_tools as ft

        ft._firecrawl_breaker.record_success()
        source = ft.scrape_url("https://example.com/hello")

    assert source is not None
    assert source.url == "https://example.com/hello"
    assert "Hello" in (source.markdown or "")
    assert source.source_type == "scrape"


def test_scrape_url_missing_key_raises():
    with patch("src.tools.firecrawl_tools.get_firecrawl_api_key", return_value=None):
        from src.tools import firecrawl_tools as ft

        ft._firecrawl_breaker.record_success()
        with pytest.raises(ValueError, match="FIRECRAWL_API_KEY"):
            ft.get_firecrawl_client()


# ---------- Agents (mocked tools / LLM) ----------

def _minimal_state(**overrides: Any) -> ResearchState:
    base: ResearchState = {
        "messages": [],
        "goal": "test research goal",
        "plan": ResearchPlan(goal="test research goal"),
        "sources": [],
        "extracted_facts": [],
        "conflicts": [],
        "next_agent": None,
        "iteration": 0,
        "max_iterations": 5,
        "report": None,
        "structured_report": None,
        "errors": [],
        "status": "running",
    }
    base.update(overrides)  # type: ignore[arg-type]
    return base


def test_discovery_node_with_mock_search():
    fake_sources = [
        Source(url="https://a.example", title="A", source_type="search", quality_score=0.6),
        Source(url="https://b.example", title="B", source_type="search", quality_score=0.55),
    ]

    with patch("src.agents.discovery.search_web", return_value=fake_sources):
        from src.agents.discovery import discovery_node

        result = discovery_node(_minimal_state())

    assert result.goto == "supervisor"
    assert "sources" in result.update
    assert len(result.update["sources"]) == 2


def test_discovery_node_soft_fails_without_key():
    with patch(
        "src.agents.discovery.search_web",
        side_effect=ValueError("FIRECRAWL_API_KEY is not set"),
    ):
        from src.agents.discovery import discovery_node

        result = discovery_node(_minimal_state())

    assert result.goto == "supervisor"
    assert result.update.get("sources") == []
    assert any("FIRECRAWL" in e or "key" in e.lower() for e in result.update.get("errors", []))


def test_gatherer_node_no_sources():
    from src.agents.gatherer import gatherer_node

    result = gatherer_node(_minimal_state(sources=[]))
    assert result.goto == "supervisor"
    assert any("empty" in e.lower() for e in result.update.get("errors", []))


def test_gatherer_node_with_mock_scrape():
    src = Source(url="https://example.com/page", title="Page", quality_score=0.7)
    scraped = Source(
        url="https://example.com/page",
        title="Page",
        markdown="# Content\n\nBody text.",
        quality_score=0.85,
        source_type="scrape",
        metadata={"from_scrape": True},
    )

    with patch("src.agents.gatherer.scrape_url", return_value=scraped):
        from src.agents.gatherer import gatherer_node

        result = gatherer_node(_minimal_state(sources=[src]))

    assert result.goto == "supervisor"
    updated = result.update["sources"]
    assert updated[0].markdown is not None
    assert "Content" in updated[0].markdown


def test_verifier_node_runs():
    from src.agents.verifier import verifier_node

    sources = [
        Source(url="https://a.example", markdown="long " * 200, quality_score=0.6),
        Source(url="https://b.example", markdown="other", quality_score=0.5),
    ]
    facts = [
        ExtractedFact(claim="Price is $10", value="$10", source_urls=["https://a.example"], confidence=0.8),
        ExtractedFact(claim="Price is $10", value="$12", source_urls=["https://b.example"], confidence=0.7),
    ]
    result = verifier_node(_minimal_state(sources=sources, extracted_facts=facts))
    assert result.goto == "supervisor"
    assert "sources" in result.update


def test_synthesizer_node_fallback_without_llm():
    """When LLM fails, synthesizer should still produce a template report."""
    sources = [Source(url="https://example.com", title="Ex", markdown="text", quality_score=0.8)]
    facts = [
        ExtractedFact(
            claim="Example claim",
            value="value",
            source_urls=["https://example.com"],
            confidence=0.7,
        )
    ]

    with patch("src.agents.synthesizer.ChatOpenAI") as mock_llm_cls:
        mock_llm_cls.return_value.invoke.side_effect = RuntimeError("no key")
        from src.agents.synthesizer import synthesizer_node

        result = synthesizer_node(
            _minimal_state(sources=sources, extracted_facts=facts)
        )

    assert result.goto == "supervisor"
    assert result.update.get("report")
    assert "Example claim" in result.update["report"] or "example.com" in result.update["report"]
    assert result.update.get("status") == "completed"


# ---------- Graph wiring (no live calls) ----------

def test_build_graph_compiles():
    from src.graph import build_graph

    graph = build_graph()
    assert graph is not None


def test_create_initial_state():
    from src.graph import create_initial_state

    state = create_initial_state("my goal", max_iterations=4)
    assert state["goal"] == "my goal"
    assert state["max_iterations"] == 4
    assert state["status"] == "running"
    assert state["sources"] == []


def test_cli_help_exits_zero():
    from src.main import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_cli_check_without_keys_exits_nonzero():
    from src.main import main

    with patch.dict("os.environ", {"OPENAI_API_KEY": "", "FIRECRAWL_API_KEY": ""}, clear=False):
        code = main(["--check"])
    assert code == 1
