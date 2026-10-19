"""Person C — Research/RMI lane.

A small, config-driven Recursive Model Index for date-key lookups, benchmarked
against a fallback lookup. The independent research core does not import the
graph/backend lane; Neo4j integration is added behind an injected fallback
interface after Person B's PRs merge.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
