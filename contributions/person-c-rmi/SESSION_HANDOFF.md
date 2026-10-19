# Session handoff — Research/RMI lane

- **Last updated:** 2026-10-19
- **Branch:** `feature/rmi-core`
- **Stage:** C1 complete and about to be checkpointed. C2 next. C4 blocked.

## Current status

- `rmi/` core is implemented: config, synthetic keys, two-stage model, error-bounded lookup, training.
- `29` unit tests pass; no Neo4j is required.
- Person B PRs #8–#12 are open and not merged; C1 was branched from `origin/main`, not from them.
- C4 (live Neo4j benchmark) is blocked until Person B merges and Aura `.env` exists.

## Last verified state

- Base: `origin/main` at `b0d9f08`.
- `python -m compileall -q rmi`: exit 0.
- `pytest rmi/tests -q`: 29 passed.
- All training keys found for uniform and clustered distributions and linear/constant model choices.
- No shared file modified; no `graphdb` import exists in `rmi/`.

## Next step

1. Checkpoint C1: commit, push, open PR C1 with base `main`.
2. Start C2 on `feature/rmi-benchmark`: benchmark harness with an injected fallback, same query set,
   latency/correctness results, tests.
3. Then C3: `retrain_rmi()` drift experiment and `RESULTS.md` draft.
4. Do not start C4 until Person B PRs #8–#12 merge and Aura exists.

## Open questions

- Is the real exported `date_key` distribution close to uniform or clustered?
- Should the final benchmark measure exact-key lookup only, or range-query latency as well?
- When Person B merges, will the fallback adapter need range-to-key translation?
- Root `RESULTS.md` will be proposed at consolidation; the draft lives in this folder meanwhile.

## Uncommitted work

All C1 files are uncommitted on `feature/rmi-core`. Nothing is staged yet.
