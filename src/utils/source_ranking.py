"""Domain priors and source quality ranking for discovery results."""

from __future__ import annotations

from urllib.parse import urlparse

from src.state import Source

_BOOST_HOST_EXACT = frozenset(
    {
        "github.com",
        "gitlab.com",
        "bitbucket.org",
        "stackoverflow.com",
        "arxiv.org",
        "npmjs.com",
        "pypi.org",
        "readthedocs.io",
    }
)

_BOOST_HOST_PREFIXES = (
    "docs.",
    "developer.",
    "developers.",
    "api.",
    "dev.",
    "learn.",
    "support.",
    "help.",
)

_BOOST_PATH_PARTS = (
    "/docs",
    "/documentation",
    "/api",
    "/reference",
    "/guide",
    "/guides",
    "/manual",
    "/tutorial",
)

_DEMOTE_HOST_EXACT = frozenset(
    {
        "youtube.com",
        "youtu.be",
        "facebook.com",
        "instagram.com",
        "tiktok.com",
        "pinterest.com",
        "reddit.com",
        "quora.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
    }
)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _path(url: str) -> str:
    try:
        return (urlparse(url).path or "").lower()
    except Exception:
        return ""


def domain_prior_delta(url: str) -> float:
    """Return a quality_score adjustment in roughly [-0.25, +0.25] based on URL structure."""
    host = _host(url)
    path = _path(url)
    if not host:
        return 0.0

    delta = 0.0

    if host in _BOOST_HOST_EXACT:
        delta += 0.15
    if any(host.startswith(p) for p in _BOOST_HOST_PREFIXES):
        delta += 0.18
    if host.endswith(".edu") or host.endswith(".gov"):
        delta += 0.12
    if any(part in path for part in _BOOST_PATH_PARTS):
        delta += 0.10

    if host in _DEMOTE_HOST_EXACT:
        delta -= 0.22
    if host == "medium.com" or host.endswith(".medium.com"):
        delta -= 0.12

    return max(-0.25, min(0.25, delta))


def apply_domain_priors(sources: list[Source]) -> list[Source]:
    """Return sources with quality_score adjusted by domain priors, sorted desc."""
    ranked: list[Source] = []
    for s in sources:
        delta = domain_prior_delta(s.url)
        new_score = max(0.0, min(1.0, s.quality_score + delta))
        meta = dict(s.metadata or {})
        if delta:
            meta["domain_prior_delta"] = round(delta, 3)
        ranked.append(s.model_copy(update={"quality_score": new_score, "metadata": meta}))

    ranked.sort(key=lambda x: x.quality_score, reverse=True)
    return ranked
