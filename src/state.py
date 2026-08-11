"""Core state schema and supporting models for the research-swarm multi-agent system."""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class Source(BaseModel):
    """A single web source collected during research."""

    url: str
    title: Optional[str] = None
    markdown: Optional[str] = None
    summary: Optional[str] = None
    quality_score: float = Field(default=0.5, ge=0.0, le=1.0)
    source_type: Literal["search", "scrape", "crawl", "map"] = "scrape"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExtractedFact(BaseModel):
    """A structured fact extracted from one or more sources."""

    claim: str
    value: str = Field(
        description="Concrete value as a short string (numbers, lists, etc. serialized to text)"
    )
    source_urls: List[str]
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    category: Optional[str] = None


class Conflict(BaseModel):
    """Detected inconsistency between sources or facts."""

    description: str
    related_facts: List[str] = Field(default_factory=list)
    severity: Literal["low", "medium", "high"] = "medium"


class ResearchPlan(BaseModel):
    """High-level research plan maintained by the supervisor."""

    goal: str
    subtasks: List[str] = Field(default_factory=list)
    completed_subtasks: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class ResearchState(TypedDict):
    """Shared state for the entire research-swarm graph."""

    messages: Annotated[List[BaseMessage], add_messages]
    goal: str
    plan: Optional[ResearchPlan]
    sources: List[Source]
    extracted_facts: List[ExtractedFact]
    conflicts: List[Conflict]
    extracted_urls: List[str]
    next_agent: Optional[
        Literal["discovery", "gatherer", "extractor", "verifier", "synthesizer", "FINISH"]
    ]
    iteration: int
    max_iterations: int
    report: Optional[str]
    structured_report: Optional[Dict[str, Any]]
    errors: List[str]
    status: Literal["running", "completed", "failed", "needs_human"]
