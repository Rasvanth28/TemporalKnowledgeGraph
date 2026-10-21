# PR C3 — Update-drift experiment and retraining metrics

- **Base branch:** `feature/rmi-benchmark` (stacked; retarget to `main` after PR #13/#14 merge)
- **Head branch:** `feature/rmi-drift`
- **PR scope:** C3
- **Suggested title:** `feat: add RMI update-drift experiment`
- **Depends on:** PR #14 (`feature/rmi-benchmark`) and PR #13. No Person B dependency.

## Summary

- Adds `rmi/drift.py`: train on an initial range, insert new keys above that range, benchmark the same
  query set before and after one manually triggered `retrain_rmi()`.
- Records before/after correctness, fallbacks, latency, and retrain duration.
- Adds `rmi/tests/test_drift.py`.
- Fills the synthetic drift section of `RESULTS.md`.

## Test results

```text
python -m compileall -q rmi
(exit 0)

python -m pytest rmi/tests -q
39 passed
```

Synthetic drift, initial=5,000 / new=500 / queries=500 / repeats=3:

```text
uniform:   before 0 correct / 500 fallbacks -> after 500 correct / 0 fallbacks; retrain 3.8 ms
clustered: before 0 correct / 500 fallbacks -> after 500 correct / 0 fallbacks; retrain 4.9 ms
```

## Known limitations

- Synthetic drift is not real news-event drift.
- Clustered keys remain slow after retraining.
- No live Neo4j or real exported key distribution; C4 is blocked by Person B and Aura.

## Review focus

1. `rmi/drift.py` — out-of-range construction, same query set before/after, retrain timing.
2. `rmi/tests/test_drift.py` — recovery, determinism, CLI.
3. `contributions/person-c-rmi/RESULTS.md` — observed drift table.
4. `contributions/person-c-rmi/decisions/ADR-0003-retrain-drift-experiment.md` — accepted design.
