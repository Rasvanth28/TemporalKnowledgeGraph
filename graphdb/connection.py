"""Small Neo4j driver/session wrapper.

The wrapper is deliberately thin: tests can inject a fake driver, and callers
never need to know how the driver was constructed.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator, Mapping

from neo4j import Driver, GraphDatabase

from graphdb.config import Neo4jConfig


class Neo4jClient:
    """A minimal connection wrapper around the official Neo4j driver."""

    def __init__(self, config: Neo4jConfig, driver: Driver | None = None):
        self.config = config
        self._driver = driver or GraphDatabase.driver(
            config.uri, auth=(config.user, config.password)
        )

    @property
    def driver(self) -> Driver:
        return self._driver

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    @contextmanager
    def session(self, database: str | None = None) -> Iterator[Any]:
        session = self._driver.session(database=database or self.config.database)
        try:
            yield session
        finally:
            session.close()

    def run(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        database: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run a query and return plain dictionaries, never driver records."""

        with self.session(database) as session:
            result = session.run(query, dict(parameters or {}))
            return [record.data() for record in result]

    def execute_write(
        self,
        work: Callable[[Any], Any],
        database: str | None = None,
    ) -> Any:
        with self.session(database) as session:
            return session.execute_write(work)

    def execute_read(
        self,
        work: Callable[[Any], Any],
        database: str | None = None,
    ) -> Any:
        with self.session(database) as session:
            return session.execute_read(work)

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
