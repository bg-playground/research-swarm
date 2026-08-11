# research-swarm

Multi-agent research system built with **LangGraph** + **Firecrawl**.

A supervisor routes work across specialized agents (Discovery → Gatherer → Extractor → Verifier → Synthesizer) to produce cited research reports from the live web.

> **Status:** Supervisor + specialist stubs + full graph wiring are in place.  
> Next up: real Firecrawl tool implementations.

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
└── agents/
    ├── supervisor.py
    ├── discovery.py
    ├── gatherer.py
    ├── extractor.py
    ├── verifier.py
    └── synthesizer.py
```

## Quick Start (stub mode)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
# OPENAI_API_KEY is required only when the real supervisor LLM is used.
# The current stubs themselves do not call external services.

python -m src.main "Your research goal here"
# or
python examples/run_stub.py "Your research goal here"
```

## License

MIT
