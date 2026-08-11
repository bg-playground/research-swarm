# 🐝 research-swarm

**Multi-agent research that actually finishes.**

Give it a goal → a LangGraph supervisor routes **Discovery → Gatherer → Extractor → Verifier → Synthesizer** → you get a **cited markdown report** from the live web via [Firecrawl](https://github.com/firecrawl/firecrawl).

[![CI](https://github.com/bg-playground/research-swarm/actions/workflows/ci.yml/badge.svg)](https://github.com/bg-playground/research-swarm/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

```text
  goal ──► supervisor ──┬── discovery   (Firecrawl Search)
                        ├── gatherer    (parallel scrape + retry)
                        ├── extractor   (structured facts)
                        ├── verifier    (conflicts / quality)
                        └── synthesizer ──► cited report
```

---

## Why this exists

Most “research agents” are either a single ReAct loop that drifts, or a heavy framework that’s hard to read.

**research-swarm** stays small and explicit:

| | |
|---|---|
| **Good for** | Competitive intel, product / landscape research, docs deep-dives, source-backed briefings |
| **Not for** | Bulk site scraping, authenticated browser flows (yet), long-running monitors |

Resilience is built in: circuit breaker, rate-limit backoff, gatherer retry, concurrency cap (3 scrapes/turn).

---

## Quick start

```bash
git clone https://github.com/bg-playground/research-swarm.git
cd research-swarm
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .

cp .env.example .env
# Set OPENAI_API_KEY and FIRECRAWL_API_KEY

python -m src.main --check
python -m src.main "Summarize core Firecrawl API concepts from docs.firecrawl.dev for agent builders"
```

Or after install: `research-swarm "Your research goal"` · `research-swarm --help`

---

## Example goals

| Example | Try |
|---------|-----|
| [Competitor pricing](examples/01_competitor_pricing.md) | `python -m src.main "Compare Firecrawl and traditional scrapers for LLM agents"` |
| [OSS landscape](examples/02_oss_landscape.md) | `python -m src.main "Map open-source web data APIs aimed at AI agents"` |
| [Docs deep-dive](examples/03_docs_deep_dive.md) | `python -m src.main "From docs.firecrawl.dev, summarize search, scrape, crawl, map, interact"` |

---

## What a run looks like

```text
🐝  research-swarm
────────────────────────────────────────
Goal            Summarize core concepts…
Max iterations  8
────────────────────────────────────────
  discovery   → 6 sources
  gatherer    → 3 scraped
  extractor   → 5 facts
  verifier    → 0 conflicts
  synthesizer → report ready
────────────────────────────────────────
✓ completed · 6 iterations · 6 sources · 5 facts
```

Reports are markdown: executive summary, key findings, sources, gaps.

---

## Configuration

| Variable | Required | Notes |
|----------|----------|--------|
| `OPENAI_API_KEY` | Yes | Supervisor / extractor / synthesizer |
| `FIRECRAWL_API_KEY` | Yes | Live search & scrape |
| `FIRECRAWL_API_URL` | No | Self-hosted Firecrawl |
| `RESEARCH_SWARM_MODEL` | No | Default `gpt-4o-mini` |
| `RESEARCH_SWARM_TEMPERATURE` | No | Default `0` |
| `RESEARCH_SWARM_LOG_LEVEL` | No | `DEBUG` / `INFO` / … |
| `LANGCHAIN_TRACING_V2` | No | Set `true` + `LANGCHAIN_API_KEY` for LangSmith |

---

## Project layout

```text
src/
├── graph.py · state.py · main.py · config.py
├── tools/firecrawl_tools.py
├── utils/circuit_breaker.py · logging_setup.py
└── agents/  supervisor · discovery · gatherer · extractor · verifier · synthesizer
examples/   01_competitor_pricing · 02_oss_landscape · 03_docs_deep_dive
tests/      smoke tests (no API keys required)
```

```bash
pip install -e ".[dev]" && pytest tests/ -v
```

---

## Responsible use

Respect site terms and `robots.txt`. Rate-limit backoff, concurrency caps, and the circuit breaker exist to reduce load — don’t strip them for aggressive crawling. Built for research and synthesis, not bulk harvesting.

---

## License

MIT
