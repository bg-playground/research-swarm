# Example 2 — Open-source landscape

## Goal to run

```bash
python -m src.main "Map the open-source landscape for web data APIs and crawlers aimed at AI agents (Firecrawl, Crawl4AI, and similar projects). Summarize positioning and notable features."
```

## What this exercises

- Broad discovery across GitHub + docs + blogs
- Multiple sources with varying quality scores
- Extractor pulling “positioning” style facts
- Synthesizer organizing a landscape overview

## Expected report shape (illustrative)

```markdown
# Research Report

**Goal:** Map the open-source landscape for web data APIs …

## Executive summary
Several open-source projects target LLM-ready web data. Firecrawl emphasizes …
Crawl4AI focuses on … Other notable projects include …

## Landscape

### Firecrawl
- License / stars / focus: …
- Notable capabilities: search, scrape, crawl, map, interact, …

### Crawl4AI
- …

### Others worth watching
- …

## Gaps / open questions
- …

## Sources
1. …
```

## Tips

- Landscape goals benefit from a slightly higher `max_iterations` if you expose it in the CLI later.
- Verifier may surface low-severity conflicts when different sites list different star counts or feature sets.
