# Session handoff — Research/RMI lane

- **Last updated:** 2026-10-19
- **Branch:** `feature/rmi-benchmark`
- **Stage:** C1 committed and PR #13 open. C2 implementation complete and about to be checkpointed. C3 next.
  C4 blocked.

## Current status

- `rmi/` core and benchmark harness are implemented and tested.
- `35` unit tests pass; no Neo4j is required.
- Person B PRs #8–#12 remain open; C branches were created from `main`/C1, not from Person B branches.
- C4 is blocked until Person B merges and Aura `.env` exists.

## Last verified state

- C1 commit: `ffc2b06` on `feature/rmi-core`; PR #13 open against `main`.
- C2 files: `rmi/fallback.py`, `rmi/benchmark.py`, `rmi/tests/test_benchmark.py`.
- `python -m compileall -q rmi`: exit 0.
- `pytest rmi/tests -q`: 35 passed.
- Synthetic benchmark (uniform, 10k keys, 2k queries, repeats=3): RMI correct 2000, fallbacks 0,
  RMI median 4,400 ns, `bisect` median 200 ns, speedup 0.045.
- Synthetic benchmark (clustered): RMI median 37,600 ns, fallback median 200 ns.
- The synthetic RMI is currently slower than the in-process `bisect` stand-in. This is recorded as a real
  negative independent result, not the final Neo4j comparison.

## Next step

1. Checkpoint C2: commit, push, open PR C2 with base `feature/rmi-core`.
2. Start C3 on `feature/rmi-drift`: `retrain_rmi()` drift experiment, before/after metrics, `RESULTS.md`
   update, tests.
3. Do not start C4 until Person B PRs #8–#12 merge and Aura exists.

## Open questions

- The real exported `date_key` distribution may be neither uniform nor clustered.
- The final benchmark may need range-query latency in addition to exact-key latency.
- The C4 adapter must map Person B's range-query API to the exact-key benchmark contract.

## Uncommitted work

C2 files and documentation updates are uncommitted on `feature/rmi-benchmark`. C1 is committed on
`feature/rmi-core`; nothing is staged yet.
