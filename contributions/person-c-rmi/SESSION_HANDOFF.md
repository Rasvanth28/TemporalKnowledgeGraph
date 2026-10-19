# Session handoff — Research/RMI lane

- **Last updated:** 2026-10-19
- **Branch:** `feature/rmi-drift`
- **Stage:** C1 PR #13 open, C2 PR #14 open, C3 implementation complete and about to be checkpointed.
  C4 is blocked.

## Current status

- RMI core, benchmark harness, and update-drift experiment are implemented and tested.
- `39` unit tests pass; no Neo4j is required.
- Person B PRs #8–#12 remain open; C branches are stacked on C1/C2, not on Person B branches.
- C4 is blocked until Person B merges and Aura `.env` exists.

## Last verified state

- C1 commit: `ffc2b06` on `feature/rmi-core`; PR #13 open against `main`.
- C2 commit: `e0f8d1f` on `feature/rmi-benchmark`; PR #14 open against `feature/rmi-core`.
- C3 files: `rmi/drift.py`, `rmi/tests/test_drift.py`.
- `python -m compileall -q rmi`: exit 0.
- `pytest rmi/tests -q`: 39 passed.
- Uniform drift: before 0 correct / 500 fallbacks; after 500 correct / 0 fallbacks; retrain 3.8 ms.
- Clustered drift: before 0 / 500; after 500 / 0; retrain 4.9 ms.
- C2 synthetic benchmark: RMI slower than the in-process `bisect` stand-in; recorded as a real negative
  independent result, not the final Neo4j B+tree comparison.

## Next step

1. Checkpoint C3: commit, push, open PR C3 with base `feature/rmi-benchmark`.
2. Do **not** start C4. C4 requires Person B PRs #8–#12 to merge and Aura `.env` to exist.
3. When Person B is merged, create `feature/rmi-neo4j-integration` from updated `main`, wire
   `graphdb.queries`, run the live benchmark, and finalize `RESULTS.md`.

## Open questions

- The real exported `date_key` distribution may differ from synthetic uniform/clustered.
- The final benchmark may need range-query latency in addition to exact-key latency.
- The C4 adapter must map Person B's range-query API to the exact-key benchmark contract.
- Root `RESULTS.md` will be proposed at consolidation; the draft is in this folder.

## Uncommitted work

C3 files and documentation are uncommitted on `feature/rmi-drift`. Nothing is staged yet.
