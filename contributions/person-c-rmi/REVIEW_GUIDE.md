# Review guide — Research/RMI lane

## 1. Motivation

Neo4j answers date-key lookups with a B+ tree. This lane tests whether a learned index can predict the key
position faster while keeping correctness through error-bounded search and a fallback.

## 2. Recommended inspection order

1. [README.md](README.md) — status, PR map, dependencies.
2. [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) — requirements and acceptance criteria.
3. [ARCHITECTURE.md](ARCHITECTURE.md) and [diagrams/architecture.md](diagrams/architecture.md).
4. [decisions/](decisions/README.md) — the three ADRs.
5. `rmi/config.py`, `rmi/keys.py`, `rmi/model.py`, `rmi/train.py`.
6. [TESTING.md](TESTING.md) — exact commands and observed results.
7. [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) — why the code looks the way it does.

## 3. Representative trace

```text
generate_sorted_keys(100, uniform, seed=42)
  -> RMIModel(RMIConfig(bucket_count=8)).fit(keys)
  -> stage 1: key -> normalized position -> bucket
  -> stage 2: key -> local position inside bucket
  -> lookup(key):
       reject out of [min_key, max_key] -> fallback "out_of_range"
       predict bucket
       search candidate buckets within stage1_error_buckets
       search local positions within stage2_errors[bucket]
       return exact index or fallback "not_found"
```

Observed for this trace: `100/100` training keys found, `stage1_error_buckets=1`, `max_stage2_error=3`.

## 4. Key functions

| Function | What to check |
|---|---|
| `load_rmi_config` | Env-driven stage models/bucket count and clear errors |
| `generate_sorted_keys` | Deterministic, sorted, unique, bounded distributions |
| `RMIModel.fit` | Bucket split, stage models, error bounds |
| `RMIModel.lookup` | Fallback reasons, bounded candidate search, exact index |
| `train_rmi` / `retrain_rmi` | Idempotent retraining entry point |

## 5. Decisions and rationale

- Two-stage RMI with config-driven model names: ADR-0001.
- Injected fallback and same-query-set benchmark: ADR-0002.
- Idempotent retraining and drift experiment: ADR-0003.

## 6. How to interpret tests

- `29 passed` in C1 means the independent core is correct on synthetic keys.
- A found training key with `candidates_checked < key_count` shows bounded search, not a scan.
- `out_of_range` and `not_found` are expected fallbacks, not failures.
- Any live Neo4j number must come from C4 and be recorded in `RESULTS.md`; synthetic numbers are not the
  final verdict.

## 7. Limitations and risks

- Two-stage only; more stages are a backlog extension.
- Synthetic distributions may not match the real exported key distribution.
- The benchmark fallback is injected; the real B+ tree measurement is blocked on Person B and Aura.
- A negative result (RMI slower than B+ tree) is a valid finding and must be reported as such.
