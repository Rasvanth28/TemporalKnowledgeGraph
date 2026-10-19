# ADR-0002 — Injected fallback and same-query-set benchmark contract

- **Status:** Accepted
- **Decision date:** 2026-10-19

## Context

The RMI must be compared against a correct fallback on the same query set. During C1–C3, Person B's
`graphdb.queries` functions are not on `main`, so importing them would couple the RMI lane to unmerged
work.

## Requirements and constraints

- C1–C3 must run without Neo4j.
- The benchmark must compare RMI and fallback on identical query keys.
- The live Neo4j fallback must be swappable in C4 without changing benchmark logic.
- No module-level import of `graphdb` in the RMI core.

## Alternatives considered

1. **Import `graphdb.queries` now.** Rejected: it is not on `main` until Person B's PRs merge.
2. **Branch from Person B's branch.** Rejected: it mixes lanes and makes review harder.
3. **Skip the benchmark until Aura exists.** Rejected: the harness and correctness checks can be built now.
4. **Inject a fallback callable.** Chosen.

## Decision

Define a fallback contract in C2:

```python
FallbackLookup = Callable[[int], int | None]
```

- C1–C3 use an injected binary-search fallback for synthetic benchmarks.
- The benchmark records `rmi_ms`, `fallback_ms`, correctness counts, and fallback counts on the same query
  keys.
- C4 adds a thin adapter around `graphdb.queries.events_in_date_range` and `event_by_id` and injects it,
  without changing the benchmark harness.

## Reasons

- Keeps the research lane independent while Person B is under review.
- Makes correctness comparisons honest: both paths see the same keys.
- Keeps the integration change small and reviewable in C4.

## Consequences and trade-offs

- Independent synthetic benchmarks are not the final Neo4j-vs-RMI result.
- The binary-search fallback is a stand-in, not a B+ tree measurement.
- C4 must map Person B's range-query API to the exact-key benchmark contract.

## Evidence

- [PROJECT_PLAN.md](../../../PROJECT_PLAN.md) says Person C can start against synthetic sorted keys and
  switch to Person B's real export later. [VERIFIED]
- Person B's query functions are stable contracts but are not yet merged to `main`. [VERIFIED]

## Conditions to revisit

- Person B's API shape changes before merge.
- The live fallback needs a different callable signature.
- The benchmark must measure range queries rather than exact-key lookups.
