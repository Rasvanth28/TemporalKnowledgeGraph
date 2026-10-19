# PR 0005 — Graph event-key export, end-to-end integration, final audit

- **Base branch:** `feature/graphdb-api` (stacked; retarget to `main` after the earlier PRs merge)
- **Head branch:** `feature/graphdb-export-e2e`
- **PR scope:** Stage 5 + Stage 6
- **Suggested title:** `feat: add graph event-key export and end-to-end verification`

## Summary

Completes the lane:

- `graphdb/export.py` exports flat event-key rows from Neo4j with the same columns and `date_key` contract
  as `pipeline/export.py`;
- unit tests cover date-key computation, sorting, CSV header/columns, missing article ids, and row
  filtering;
- an integration test populates the fixture and compares graph rows to the pipeline contract;
- an end-to-end integration test runs `data/sample_articles.json` through Person A's pipeline, writes to
  Neo4j, performs query round-trips, and compares graph export rows with the pipeline CSV;
- [FINAL_AUDIT.md](../FINAL_AUDIT.md) records deliverables, verification status, PR map, limitations, and
  reviewer checklist.

## Test results

```text
pytest graphdb/tests -m "not integration"   64 passed, 5 deselected
pytest -q                                   106 passed, 5 skipped, 1 warning
pip check                                   No broken requirements found.
compileall graphdb                          exit 0
```

The five skipped tests are the real-Neo4j integration tests. They are not passes.

## Known limitations

- Live Aura export, query, API, and index evidence are unexecuted until `.env` exists.
- The end-to-end test cleans exact pipeline ids; those official-sample ids are uuid5-based, not
  `test_`-prefixed. Cleanup is exact and never wipes the database.
- Year-only dates, stale `LINKED_TO`, and global `PRECEDES` scale behavior remain documented limitations.

## Review focus

1. `graphdb/export.py` — graph-sourced export and stable column/date-key contract.
2. `graphdb/tests/test_export_unit.py` — column contract and CSV behavior.
3. `graphdb/tests/test_export_neo4j.py` — graph export versus pipeline contract (skipped here).
4. `graphdb/tests/test_e2e_pipeline_neo4j.py` — official sample round-trip (skipped here).
5. [FINAL_AUDIT.md](../FINAL_AUDIT.md) — lane completion matrix.
