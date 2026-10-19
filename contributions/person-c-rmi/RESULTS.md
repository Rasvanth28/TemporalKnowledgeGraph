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

Pending. Will record, on the same query set:

- RMI median/mean lookup latency;
- fallback median/mean lookup latency;
- correctness counts;
- fallback counts and reasons.

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
