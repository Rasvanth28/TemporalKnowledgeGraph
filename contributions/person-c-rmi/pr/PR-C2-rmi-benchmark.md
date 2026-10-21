# PR C2 — RMI benchmark harness with injected fallback

- **Base branch:** `feature/rmi-core` (stacked; retarget to `main` after PR #13 merges)
- **Head branch:** `feature/rmi-benchmark`
- **PR scope:** C2
- **Suggested title:** `feat: add RMI benchmark harness`
- **Depends on:** PR #13 (`feature/rmi-core`). No Person B dependency.

## Summary

- Adds `rmi/fallback.py` with the injectable `FallbackLookup` contract and a `bisect` stand-in.
- Adds `rmi/benchmark.py`: same-query-set RMI-vs-fallback latency and correctness harness.
- Adds CLI: `python -m rmi.benchmark`.
- Adds a scalar `predict_scalar` fast path to the model hot loop after the first benchmark exposed numpy
  allocation overhead.
- Records synthetic uniform and clustered results in `RESULTS.md`.

## Test results

```text
python -m compileall -q rmi
(exit 0)

python -m pytest rmi/tests -q
35 passed
```

Synthetic benchmark, 10,000 keys / 2,000 queries / repeats=3:

```text
uniform:   rmi correct 2000, fallbacks 0, RMI median 4,400 ns, fallback median 200 ns
clustered: rmi correct 2000, fallbacks 0, RMI median 37,600 ns, fallback median 200 ns
```

## Known limitations

- The fallback is an in-process `bisect` stand-in, not a Neo4j B+ tree.
- The current RMI is slower than `bisect` on synthetic keys; this is recorded as a valid negative result.
- No live Neo4j comparison yet; C4 is blocked by Person B PRs #8–#12 and Aura.

## Review focus

1. `rmi/benchmark.py` — same query set, correctness counts, fallback counts, timing percentiles.
2. `rmi/fallback.py` — injectable contract for C4.
3. `rmi/model.py` — scalar prediction fast path.
4. `contributions/person-c-rmi/RESULTS.md` — honest synthetic result.
