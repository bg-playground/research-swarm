"""Specialist agents for the research-swarm."""

from .discovery import discovery_node
from .extractor import extractor_node
from .gatherer import gatherer_node
from .supervisor import supervisor_node
from .synthesizer import synthesizer_node
from .verifier import verifier_node

__all__ = [
    "supervisor_node",
    "discovery_node",
    "gatherer_node",
    "extractor_node",
    "verifier_node",
    "synthesizer_node",
]
