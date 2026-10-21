# PR 0002 — Idempotent Neo4j writer

- **Base branch:** `feature/graphdb-foundation` (stacked; retarget to `main` after PR 1 merges)
- **Head branch:** `feature/graphdb-writer`
- **PR scope:** Stage 2
- **Suggested title:** `feat: add idempotent Neo4j writer`

## Summary

Implements the writer that consumes Person A's `PipelineOutput`:

- accepts `PipelineOutput` objects or the `pipeline_output.json` shape;
- validates link endpoints against both the batch and the existing graph before writing;
- uses parameterized `UNWIND` + `MERGE` inside explicit transactions;
- creates `DESCRIBES`, `MENTIONS`, `Event-ABOUT`, derived `Article-ABOUT`, `INVOLVES`, and `LINKED_TO`;
- applies latest-input-wins to `LINKED_TO` confidence/reason;
- rebuilds the global `(date, id)` `PRECEDES` chain in one transaction after each batch;
- returns created-vs-matched node and relationship counts;
- ships a synthetic test fixture and unit tests.

## Test results

```text
pytest graphdb/tests -m "not integration"   33 passed, 2 deselected
pytest -q                                   75 passed, 2 skipped
pip check                                   No broken requirements found.
compileall graphdb                          exit 0
```

The writer integration test is skipped until `NEO4J_URI` is configured. It exercises write → write again →
insert out-of-order event and asserts the PRECEDES chain remains correct with no duplicates.

## Known limitations

- Live idempotency proof is pending Aura.
- Stale `LINKED_TO` edges are not deleted by default.
- Global `PRECEDES` rebuild is a batch operation and will need redesign at larger scale.

## Review focus

1. `graphdb/writer.py` — validation happens before any write; markers are removed in-transaction.
2. `graphdb/tests/fixtures/pipeline_output.json` — test-only, `test_`-prefixed ids.
3. `graphdb/tests/test_writer_plan.py` — derived rows, dedupe, ordering, parsing errors.
4. `graphdb/tests/test_writer_validation.py` — missing endpoints and database-existing endpoints.
5. `graphdb/tests/test_writer_neo4j.py` — the live idempotency/out-of-order test (skipped here).
