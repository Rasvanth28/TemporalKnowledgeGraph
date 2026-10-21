"""Apply and verify the approved Neo4j indexes and constraints.

Schema operations are idempotent. The script applies constraints first (they
are required for safe MERGE behavior), then the four design-document indexes,
and finally verifies property coverage with SHOW INDEXES / SHOW CONSTRAINTS.

A uniqueness constraint creates its own backing index. Some Neo4j versions
therefore report an equivalent schema object instead of allowing a separate
index with the same property. That case is reported and verified, not hidden.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Any

from graphdb.config import ConfigurationError, Neo4jConfig, load_neo4j_config
from graphdb.connection import Neo4jClient

_GRAPHDB_DIR = Path(__file__).resolve().parent
INDEXES_FILE = _GRAPHDB_DIR / "indexes.cql"
CONSTRAINTS_FILE = _GRAPHDB_DIR / "constraints.cql"

REQUIRED_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("event_date", "Event", "date"),
    ("event_type", "Event", "type"),
    ("entity_name", "Entity", "name"),
    ("topic_name", "Topic", "name"),
)

REQUIRED_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    ("article_id_unique", "Article", "id"),
    ("event_id_unique", "Event", "id"),
    ("entity_id_unique", "Entity", "id"),
    ("topic_name_unique", "Topic", "name"),
)

SHOW_INDEXES_QUERY = "SHOW INDEXES"
SHOW_CONSTRAINTS_QUERY = "SHOW CONSTRAINTS"


class SchemaApplicationError(RuntimeError):
    """Raised when the requested schema cannot be verified."""

    def __init__(self, message: str, report: "SchemaReport | None" = None):
        super().__init__(message)
        self.report = report


@dataclass(frozen=True)
class SchemaCheck:
    kind: str
    label: str
    property: str
    required_name: str
    satisfied_by: str | None = None
    exact: bool = False

    @property
    def ok(self) -> bool:
        return self.satisfied_by is not None


@dataclass(frozen=True)
class SchemaReport:
    indexes: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[dict[str, Any]] = field(default_factory=list)
    index_checks: list[SchemaCheck] = field(default_factory=list)
    constraint_checks: list[SchemaCheck] = field(default_factory=list)
    equivalent_conflicts: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.index_checks + self.constraint_checks)

    @property
    def missing(self) -> list[SchemaCheck]:
        return [check for check in self.index_checks + self.constraint_checks if not check.ok]


def read_statements(path: str | Path) -> list[str]:
    """Read semicolon-separated CQL statements, ignoring ``//`` comments."""

    text = Path(path).read_text(encoding="utf-8")
    without_comments = "\n".join(line.split("//", 1)[0] for line in text.splitlines())
    return [statement.strip() for statement in without_comments.split(";") if statement.strip()]


def _is_equivalent_schema_error(exc: Exception) -> bool:
    code = str(getattr(exc, "code", "") or "").lower()
    message = str(exc).lower()
    return (
        "equivalentschemarulealreadyexists" in code
        or "equivalent schema rule" in message
        or "equivalent index already exists" in message
    )


def _labels_or_types(record: dict[str, Any]) -> list[str]:
    value = record.get("labelsOrTypes") or []
    return [str(item) for item in value]


def _properties(record: dict[str, Any]) -> list[str]:
    value = record.get("properties") or []
    return [str(item) for item in value]


def _is_online(record: dict[str, Any]) -> bool:
    state = record.get("state")
    return state is None or str(state).upper() == "ONLINE"


def _index_matches(record: dict[str, Any], label: str, prop: str) -> bool:
    return (
        str(record.get("entityType", "")).upper() == "NODE"
        and label in _labels_or_types(record)
        and prop in _properties(record)
        and _is_online(record)
    )


def _constraint_matches(record: dict[str, Any], label: str, prop: str) -> bool:
    constraint_type = str(record.get("type", "")).upper()
    return (
        "UNIQUENESS" in constraint_type
        and label in _labels_or_types(record)
        and prop in _properties(record)
    )


def show_indexes(client: Neo4jClient) -> list[dict[str, Any]]:
    return client.run(SHOW_INDEXES_QUERY)


def show_constraints(client: Neo4jClient) -> list[dict[str, Any]]:
    return client.run(SHOW_CONSTRAINTS_QUERY)


def build_report(client: Neo4jClient, conflicts: list[str] | None = None) -> SchemaReport:
    indexes = show_indexes(client)
    constraints = show_constraints(client)

    index_checks: list[SchemaCheck] = []
    for required_name, label, prop in REQUIRED_INDEXES:
        candidates = [item for item in indexes if _index_matches(item, label, prop)]
        exact = next((item for item in candidates if item.get("name") == required_name), None)
        chosen = exact or (candidates[0] if candidates else None)
        index_checks.append(
            SchemaCheck(
                kind="index",
                label=label,
                property=prop,
                required_name=required_name,
                satisfied_by=str(chosen.get("name")) if chosen else None,
                exact=exact is not None,
            )
        )

    constraint_checks: list[SchemaCheck] = []
    for required_name, label, prop in REQUIRED_CONSTRAINTS:
        candidates = [item for item in constraints if _constraint_matches(item, label, prop)]
        exact = next((item for item in candidates if item.get("name") == required_name), None)
        chosen = exact or (candidates[0] if candidates else None)
        constraint_checks.append(
            SchemaCheck(
                kind="constraint",
                label=label,
                property=prop,
                required_name=required_name,
                satisfied_by=str(chosen.get("name")) if chosen else None,
                exact=exact is not None,
            )
        )

    return SchemaReport(
        indexes=indexes,
        constraints=constraints,
        index_checks=index_checks,
        constraint_checks=constraint_checks,
        equivalent_conflicts=list(conflicts or []),
    )


def _wait_for_online(client: Neo4jClient, timeout: float) -> None:
    if timeout <= 0:
        return
    deadline = time.monotonic() + timeout
    while True:
        indexes = show_indexes(client)
        pending = [item for item in indexes if not _is_online(item)]
        if not pending or time.monotonic() >= deadline:
            return
        time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))


def apply_schema(client: Neo4jClient, wait_seconds: float = 30.0) -> SchemaReport:
    """Apply constraints then indexes, wait for ONLINE state, and verify coverage."""

    conflicts: list[str] = []
    for statement in read_statements(CONSTRAINTS_FILE) + read_statements(INDEXES_FILE):
        try:
            client.run(statement)
        except Exception as exc:
            if _is_equivalent_schema_error(exc):
                conflicts.append(f"{statement}: {type(exc).__name__}: {exc}")
                continue
            raise

    _wait_for_online(client, wait_seconds)
    report = build_report(client, conflicts=conflicts)
    if not report.ok:
        missing = ", ".join(
            f"{check.label}.{check.property} ({check.required_name})"
            for check in report.missing
        )
        raise SchemaApplicationError(
            "Neo4j schema verification failed; missing coverage: " + missing,
            report=report,
        )
    return report


def verify_schema(client: Neo4jClient) -> SchemaReport:
    """Verify the live schema without applying anything."""

    return build_report(client)


def _report_lines(report: SchemaReport) -> list[str]:
    status = "OK" if report.ok else "FAILED"
    lines = [f"Schema verification: {status}"]

    covered_indexes = sum(1 for check in report.index_checks if check.ok)
    covered_constraints = sum(1 for check in report.constraint_checks if check.ok)
    lines.append(f"indexes: {covered_indexes}/{len(report.index_checks)} covered")
    for check in report.index_checks:
        state = f"exact ({check.satisfied_by})" if check.exact else (
            f"equivalent ({check.satisfied_by})" if check.ok else "MISSING"
        )
        lines.append(f"  {check.required_name}: {state}")

    lines.append(
        f"constraints: {covered_constraints}/{len(report.constraint_checks)} covered"
    )
    for check in report.constraint_checks:
        state = "exact" if check.exact else ("equivalent" if check.ok else "MISSING")
        lines.append(f"  {check.label}.{check.property}: {state} ({check.satisfied_by or '-'})")

    if report.equivalent_conflicts:
        lines.append(f"equivalent schema conflicts handled: {len(report.equivalent_conflicts)}")
        for conflict in report.equivalent_conflicts:
            lines.append(f"  {conflict}")

    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply and verify the Neo4j indexes and constraints."
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Inspect the live schema without creating indexes or constraints.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Seconds to wait for index population (default: 30).",
    )
    args = parser.parse_args(argv)

    try:
        config: Neo4jConfig = load_neo4j_config()
    except ConfigurationError as exc:
        print("Schema operation: FAILED")
        print(f"configuration error: {exc}")
        return 1

    client = Neo4jClient(config)
    try:
        report = verify_schema(client) if args.verify_only else apply_schema(
            client, wait_seconds=args.timeout
        )
    except SchemaApplicationError as exc:
        lines = _report_lines(exc.report) if exc.report else [str(exc)]
        for line in lines:
            print(line)
        return 1
    except Exception as exc:
        print(f"Schema operation: FAILED ({type(exc).__name__}: {exc})")
        return 1
    finally:
        client.close()

    for line in _report_lines(report):
        print(line)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
