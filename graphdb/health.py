"""Neo4j connectivity and server-metadata health check."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from typing import Any

from graphdb.config import ConfigurationError, Neo4jConfig, load_neo4j_config
from graphdb.connection import Neo4jClient

_COMPONENTS_QUERY = (
    "CALL dbms.components() "
    "YIELD name, versions, edition "
    "RETURN name, versions[0] AS version, edition"
)


@dataclass(frozen=True)
class HealthReport:
    connected: bool
    database: str
    server_version: str | None = None
    edition: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _redact(message: str, secret: str) -> str:
    return message.replace(secret, "***") if secret else message


def check_health(
    config: Neo4jConfig,
    client: Neo4jClient | None = None,
) -> HealthReport:
    """Check connectivity and return server metadata.

    If ``client`` is omitted, this function owns and closes a temporary client.
    The password is redacted from any error text before it is returned.
    """

    owns_client = client is None
    client = client or Neo4jClient(config)

    try:
        client.verify_connectivity()

        try:
            rows = client.run(_COMPONENTS_QUERY, database=config.database)
        except Exception:
            rows = []

        if rows:
            row = rows[0]
            return HealthReport(
                connected=True,
                database=config.database,
                server_version=str(row.get("version")) if row.get("version") else None,
                edition=str(row.get("edition")) if row.get("edition") else None,
            )

        # A very restricted server may allow connectivity but not dbms.components.
        client.run("RETURN 1 AS ok", database=config.database)
        return HealthReport(connected=True, database=config.database)
    except Exception as exc:  # health reports failures instead of crashing the CLI
        message = _redact(f"{type(exc).__name__}: {exc}", config.password)
        return HealthReport(
            connected=False,
            database=config.database,
            error=message,
        )
    finally:
        if owns_client:
            client.close()


def _print_report(report: HealthReport, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.as_dict(), indent=2))
        return

    if report.connected:
        print("Neo4j health: OK")
        print(f"database: {report.database}")
        if report.server_version:
            edition = f" ({report.edition})" if report.edition else ""
            print(f"server: Neo4j {report.server_version}{edition}")
        return

    print("Neo4j health: FAILED")
    print(f"database: {report.database}")
    if report.error:
        print(f"error: {report.error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Neo4j connectivity and metadata.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = parser.parse_args(argv)

    try:
        config = load_neo4j_config()
    except ConfigurationError as exc:
        print("Neo4j health: FAILED")
        print(f"configuration error: {exc}")
        return 1

    report = check_health(config)
    _print_report(report, args.json)
    return 0 if report.connected else 1


if __name__ == "__main__":
    raise SystemExit(main())
