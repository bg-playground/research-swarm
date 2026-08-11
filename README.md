# research-swarm

Multi-agent research system built with **LangGraph** + **Firecrawl**.

A supervisor routes work across specialized agents (Discovery → Gatherer → Extractor → Verifier → Synthesizer) to produce cited research reports from the live web.

> **Status:** Core system is live. Supervisor, real Firecrawl-powered discovery & gatherer, LLM extractor/synthesizer, and full graph wiring are in place.  
> Next up: polish, evaluation examples, and optional Interact support.

## Architecture

```
User Goal
    │
    ▼
Supervisor (plans + routes)
    ├── discovery
    ├── gatherer
    ├── extractor
    ├── verifier
    └── synthesizer → final report
         │
         └── (back to Supervisor until FINISH)
```

The graph is supervisor-centric: every specialist returns control to the supervisor via LangGraph `Command` objects. The supervisor alone decides the next specialist or `FINISH`.

## Project Layout

```
src/
├── graph.py          # StateGraph definition + helpers
├── state.py          # ResearchState + supporting models
├── main.py           # Simple CLI entry point
├── config.py
├── tools/
│   └── firecrawl_tools.py
└── agents/
    ├── supervisor.py
    ├── discovery.py
    ├── gatherer.py
    ├── extractor.py
    ├── verifier.py
    └── synthesizer.py
```

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # add OPENAI_API_KEY and FIRECRAWL_API_KEY

python -m src.main "Your research goal here"
```

## License

MIT
