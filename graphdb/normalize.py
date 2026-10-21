"""Entity-name normalization for graph lookups.

The canonical implementation now lives in ``common/names.py`` (shared with the pipeline, which
writes the names), so lookups and writes can never drift apart.
"""

from __future__ import annotations

from common.names import normalize_name


def normalize_entity_name(name: str) -> str:
    """Same normalization the pipeline applies when it stores entity names."""

    return normalize_name(name)
