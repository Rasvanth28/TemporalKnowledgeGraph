# PR 0003 — Stable query contract and fallback functions

- **Base branch:** `feature/graphdb-writer` (stacked; retarget to `main` after the earlier PRs merge)
- **Head branch:** `feature/graphdb-queries`
- **PR scope:** Stage 3
- **Suggested title:** `feat: add stable graph query contract`

## Summary

Adds the stable query layer:

- `event_by_id` and `events_in_date_range` as RMI fallback targets;
- `chain_by_entity`, `chain_by_topic`, and `chain_by_date_range`;
- exact normalized entity matching with the `entity_name` index, plus a clearly
  marked non-indexed case-insensitive fallback;
- depth/limit/min-confidence validation and chronological ordering;
- returned edges carry confidence and reason;
- `graphdb/normalize.py` mirrors Person A's entity-name normalization without importing spaCy;
- `explain_events_in_date_range` for live index evidence.

## Test results

```text
pytest graphdb/tests -m "not integration"   48 passed, 3 deselected
pytest -q                                   90 passed, 3 skipped
pip check                                   No broken requirements found.
compileall graphdb                          exit 0
```

The Neo4j integration test is skipped until `NEO4J_URI` exists. It populates the fixture, exercises the
query round-trip, and asserts the date-range `EXPLAIN` plan contains `event_date`.

## Known limitations

- Live index evidence and query results against Aura are not yet observed.
- Case-insensitive entity lookup is a non-indexed scan and only runs after an empty exact match.
- Topic matching is exact; topic names are lowercased by the pipeline.

## Review focus

1. `graphdb/queries.py` — return shapes, guards, ordering, and parameterized Cypher.
2. `graphdb/normalize.py` — parity with Person A's normalization.
3. `graphdb/tests/test_queries_unit.py` — fake-client behavior for every query path.
4. `graphdb/tests/test_queries_neo4j.py` — live round-trip and `EXPLAIN` evidence (skipped here).
