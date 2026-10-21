# Architecture Decision Records

This directory records significant decisions for the Graph DB & Backend lane. ADRs are grouped by concern,
not one per question, so the rationale stays readable.

## Status values

| Status | Meaning |
|---|---|
| `Proposed` | Under discussion; not binding. |
| `Accepted` | Approved by the owner; implementation should follow it. |
| `Superseded` | Replaced by a later ADR; keep the history. |

## Index

| ID | Title | Status | Decision date |
|---|---|---|---|
| [ADR-0001](ADR-0001-neo4j-runtime-and-test-isolation.md) | Neo4j runtime, configuration, and test isolation | Accepted | 2026-10-19 |
| [ADR-0002](ADR-0002-graph-schema-and-temporal-semantics.md) | Graph schema and temporal semantics | Accepted | 2026-10-19 |
| [ADR-0003](ADR-0003-write-idempotency-and-validation.md) | Idempotent write and validation semantics | Accepted | 2026-10-19 |
| [ADR-0004](ADR-0004-query-api-and-export-contracts.md) | Query, API, and export contracts | Accepted | 2026-10-19 |

## Template

Create the next ADR as `ADR-000N-<short-title>.md`.

```markdown
# ADR-000N — Title

- **Status:** Proposed | Accepted | Superseded
- **Decision date:** YYYY-MM-DD
- **Supersedes:** (optional)
- **Superseded by:** (optional)

## Context

What problem or mismatch requires a decision? Include verified evidence and constraints.

## Requirements and constraints

What must the decision satisfy? What is explicitly out of scope?

## Alternatives considered

List the realistic options and their trade-offs.

## Decision

State the chosen option precisely enough to implement.

## Reasons

Why this option, compared with the alternatives?

## Consequences and trade-offs

What becomes easier, harder, or impossible? What must be documented or revisited?

## Evidence

Commands, file references, design-document sections, or observed results. Never invent evidence.

## Conditions to revisit

What change would justify reopening this decision?
```
