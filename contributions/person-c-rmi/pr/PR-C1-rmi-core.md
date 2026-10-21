# PR C1 — Two-stage RMI core

- **Base branch:** `main`
- **Head branch:** `feature/rmi-core`
- **PR scope:** C1
- **Suggested title:** `feat: add two-stage RMI core`
- **Depends on:** nothing. Person B's PRs #8–#12 are not required for this PR.

## Summary

Starts the independent Research/RMI lane:

- config-driven stage model names and bucket count;
- deterministic synthetic sorted-key generators (uniform and clustered);
- two-stage RMI: stage-1 bucket router, stage-2 per-bucket local models;
- maximum-training-error correction windows that guarantee all training keys are found;
- explicit `out_of_range` and `not_found` fallback results for the later Neo4j path;
- `train_rmi`, idempotent `retrain_rmi`, and a CLI summary;
- contribution docs, ADRs, and handoff.

No `graphdb`, `common`, `pipeline`, `scripts`, root README, or shared requirements file is touched.

## Test results

```text
python -m compileall -q rmi
(exit 0)

python -m pytest rmi/tests -q
29 passed
```

Manual checks:

```text
100/100 training keys found (uniform, bucket_count=8)
500/500 training keys found (uniform and clustered, linear/constant combos)
```

## Known limitations

- Exactly two stages are implemented; other stage counts fail clearly.
- No latency comparison yet; C2 adds the injected-fallback benchmark.
- No live Neo4j; C4 is blocked by Person B PRs #8–#12 and Aura.

## Review focus

1. `rmi/model.py` — bucket split, stage models, error windows, bounded lookup.
2. `rmi/config.py` — config-driven stage/model/bucket validation.
3. `rmi/keys.py` — deterministic sorted, unique synthetic keys.
4. `rmi/tests/` — correctness for all supported model combinations.
5. `contributions/person-c-rmi/decisions/` — accepted ADRs.
