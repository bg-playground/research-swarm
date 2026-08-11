# Example 1 — Competitor pricing & features

## Goal to run

```bash
python -m src.main "Compare pricing and key features of Firecrawl, Browserbase, and traditional web scrapers for AI / LLM agent use cases"
```

## What this exercises

- Discovery (Search for vendor pages and comparisons)
- Gatherer (scrape pricing / product pages)
- Extractor (pull pricing tiers, feature claims)
- Verifier (flag conflicting numbers if sources disagree)
- Synthesizer (structured comparison report)

## Expected report shape (illustrative)

```markdown
# Research Report

**Goal:** Compare pricing and key features of Firecrawl, Browserbase, …

## Executive summary
Firecrawl positions itself as an LLM-ready web data API (search, scrape, crawl, map).
Browserbase focuses on cloud browsers / automation. Traditional scrapers …
…

## Key findings

### Firecrawl
- Pricing: … (cite source)
- Strengths for agents: clean markdown, search+scrape in one API, …
- Limits: …

### Browserbase
- …

### Traditional scrapers (e.g. Scrapy / Playwright self-hosted)
- …

## Conflicts / caveats
- Pricing pages change frequently; figures below were observed on <date>.

## Sources
1. [Firecrawl Pricing](https://…) (quality=0.9)
2. …
```

## Tips

- Prefer a narrow goal (“for AI agents”) so the supervisor stays focused.
- If you hit rate limits, the circuit breaker and backoff should soft-fail instead of crashing the run.
