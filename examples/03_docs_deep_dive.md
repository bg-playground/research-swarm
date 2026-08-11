# Example 3 — Docs / changelog deep-dive

## Goal to run

```bash
python -m src.main "Summarize the core concepts and recent notable changes in the Firecrawl documentation for someone building an AI research agent"
```

## What this exercises

- Discovery targeted at documentation domains
- Gatherer on docs pages (often JS-rendered → Firecrawl strength)
- Extractor pulling concepts, endpoints, and change notes
- Synthesizer producing a practical briefing for builders

## Expected report shape (illustrative)

```markdown
# Research Report

**Goal:** Summarize the core concepts and recent notable changes in the Firecrawl documentation …

## Executive summary
Firecrawl exposes Search, Scrape, Crawl, Map, and Interact-style capabilities optimized for LLM pipelines. Recent docs emphasize …

## Core concepts
- Scrape → clean markdown / structured extract
- Search → query + optional full page content
- Crawl / Map → site coverage vs URL discovery
- …

## Practical notes for agent builders
- …
- Rate limits and self-hosting options: …

## Sources
1. [Firecrawl Docs](https://docs.firecrawl.dev/…)
2. …
```

## Tips

- Docs sites are a sweet spot for Firecrawl (JS-heavy, but returns clean markdown).
- Keep the goal audience-specific (“for someone building an AI research agent”) so the synthesizer stays useful instead of generic.
