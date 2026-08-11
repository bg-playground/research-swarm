# research-swarm

**Multi-agent research system** built with [LangGraph](https://github.com/langchain-ai/langgraph) + [Firecrawl](https://github.com/firecrawl/firecrawl).

Give it a research goal. A supervisor routes work across specialized agents (Discovery → Gatherer → Extractor → Verifier → Synthesizer) and returns a **cited markdown report** from the live web.

> **Status:** Core system is usable. Supervisor, Firecrawl-powered discovery & gatherer (with parallel scrape, retries, rate-limit backoff, and circuit breaker), LLM extractor/synthesizer, and full graph wiring are in place.

---

## Why this exists

Most “research agents” are either:

- a single ReAct loop that gets lost on multi-step research, or  
- heavy frameworks that are hard to inspect and extend.

**research-swarm** keeps the control flow explicit (LangGraph supervisor + specialists), uses Firecrawl for reliable LLM-ready web data, and stays small enough to read in an afternoon.

**Good for:** competitive intel, product/landscape research, docs deep-dives, source-backed briefings.  
**Not for:** bulk site scraping, authenticated multi-step browser flows (yet), or long-running monitoring (use a scheduler on top).

---

## Architecture

```
User Goal
    │
    ▼
Supervisor (plans + routes)
    ├── discovery   → Firecrawl Search
    ├── gatherer    → parallel Scrape (+ retry / backoff)
    ├── extractor   → structured facts (LLM)
    ├── verifier    → quality + conflict signals
    └── synthesizer → cited report
         │
         └── back to Supervisor until FINISH
```

Resilience layers:

1. Circuit breaker (stops calling after sustained failures)  
2. Rate-limit retry with exponential backoff  
3. Gatherer-level retry pass after a short delay  
4. Concurrency cap (max 3 scrapes per turn)

---

## Quick start

```bash
git clone https://github.com/bg-playground/research-swarm.git
cd research-swarm
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .

cp .env.example .env
# Add:
#   OPENAI_API_KEY=sk-...
#   FIRECRAWL_API_KEY=fc-...

python -m src.main "Compare pricing and key features of leading web scraping APIs for AI agents"
```

Without keys the graph still runs but discovery/gatherer will soft-fail and tell you what’s missing.

---

## Example goals

| Goal | What you get |
|------|----------------|
| [Competitor pricing & features](examples/01_competitor_pricing.md) | Side-by-side style findings + sources |
| [Open-source landscape](examples/02_oss_landscape.md) | Map of tools, positioning, citations |
| [Docs / changelog deep-dive](examples/03_docs_deep_dive.md) | Structured notes from documentation sites |

Run any of them:

```bash
python -m src.main "Compare Firecrawl, Browserbase, and traditional scrapers for LLM agents"
python -m src.main "Map the open-source landscape for web data APIs aimed at AI agents"
python -m src.main "Summarize recent changes and key concepts in the Firecrawl documentation"
```

See the `examples/` folder for expected report shape and notes.

---

## Project layout

```
src/
├── graph.py              # StateGraph + run_research()
├── state.py              # ResearchState + models
├── main.py               # CLI entrypoint
├── config.py
├── tools/
│   └── firecrawl_tools.py
├── utils/
│   └── circuit_breaker.py
└── agents/
    ├── supervisor.py
    ├── discovery.py
    ├── gatherer.py
    ├── extractor.py
    ├── verifier.py
    └── synthesizer.py
examples/
├── 01_competitor_pricing.md
├── 02_oss_landscape.md
├── 03_docs_deep_dive.md
└── run_stub.py
```

---

## Configuration (env)

| Variable | Required | Notes |
|----------|----------|--------|
| `OPENAI_API_KEY` | Yes (for supervisor / extractor / synthesizer) | Any OpenAI-compatible key works if you point the client appropriately |
| `FIRECRAWL_API_KEY` | Yes (for live web) | Get one at [firecrawl.dev](https://firecrawl.dev) |
| `FIRECRAWL_API_URL` | No | For self-hosted Firecrawl |

Tunable constants live in the agents/tools (e.g. `MAX_SCRAPES_PER_TURN = 3`, circuit thresholds). They will be centralized in a later pass.

---

## Responsible use

- Respect site terms and `robots.txt`.  
- The built-in rate-limit backoff, concurrency cap, and circuit breaker are there to reduce load — do not remove them for aggressive crawling.  
- This project is for research and synthesis, not large-scale data harvesting.

---

## License

MIT
