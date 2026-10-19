"""Shared pytest setup for the RMI lane.

Integration tests in later PRs are skipped unless a Neo4j instance is
configured. The independent research core does not require Neo4j.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
import pytest

load_dotenv()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: requires a reachable Neo4j instance configured by NEO4J_*",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if os.environ.get("NEO4J_URI"):
        return
    skip = pytest.mark.skip(reason="NEO4J_URI is not set; integration test skipped")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
