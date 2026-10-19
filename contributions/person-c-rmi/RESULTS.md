# RMI results

> **Status: draft.** Synthetic results are added in C2/C3. Live RMI-vs-B+tree results require C4, which is
> blocked until Person B's PRs #8–#12 merge and a Neo4j `.env` exists.

## 1. Setup

| Item | Value |
|---|---|
| Key type | int64 `date_key` (days since 1970-01-01) |
| Key distributions | uniform and clustered synthetic keys |
| RMI stages | 2 |
| Stage models | configurable (`linear`/`constant`) |
| Correctness | error-bounded local search |
| Fallback | injected binary search in C1–C3; Neo4j in C4 |

## 2. C1 correctness

Observed:

```text
pytest rmi/tests -q                29 passed
100/100 training keys found         uniform, bucket_count=8
100/100 training keys found         clustered
500/500 training keys found         all linear/constant model combinations
```

No latency comparison is claimed yet.

## 3. C2 benchmark (synthetic)

Observed on 2026-10-19 with the in-process `bisect` stand-in fallback. 10,000 keys, 2,000 queries,
repeats=3, bucket_count=128, stage models `linear,linear`.

| Distribution | RMI correct | RMI fallbacks | Fallback correct | RMI median ns | RMI p95 ns | Fallback median ns | Fallback p95 ns | Speedup (fallback/RMI) |
|---|---|---|---|---|---|---|---|---|
| uniform | 2000 | 0 | 2000 | 4,400 | 5,700 | 200 | 300 | 0.045 |
| clustered | 2000 | 0 | 2000 | 37,600 | 84,500 | 200 | 300 | 0.005 |

Interpretation:

- The RMI finds every query; no fallback occurs on training keys.
- The independent RMI is currently **slower** than the local `bisect` fallback.
- This is a valid negative result for the synthetic setup, not the final Neo4j B+ tree result.
- `bisect` is in-process C code; the real Neo4j fallback is a network round trip. The C4 live benchmark is
  the one that answers the project's research question.
- Clustered keys increase the stage-1 error window and slow the RMI substantially. This is recorded as a
  real weakness of the current two-stage linear design.

## 4. C3 update-drift experiment

Pending. Will record before/after retraining:

- out-of-range lookup fallback rate;
- corrected lookup rate after `retrain_rmi()`;
- latency before/after;
- retrain duration.

## 5. C4 live RMI vs Neo4j B+ tree

Blocked. Requires:

- Person B PRs #8–#12 merged;
- `graphdb/queries.py` on `main`;
- a reachable Neo4j `.env`;
- the exported real event-key dataset.

Until then, any statement about RMI beating or losing to the B+ tree is unproven.
