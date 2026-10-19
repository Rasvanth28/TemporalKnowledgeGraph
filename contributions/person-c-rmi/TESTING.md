# Testing — Research/RMI lane

## 1. Environment

| Item | Value | Label |
|---|---|---|
| OS shell | Windows / PowerShell | [VERIFIED] |
| Python | 3.14.0 in `.venv` | [VERIFIED] |
| Test framework | pytest 9.1.1 | [VERIFIED] |
| NumPy | 2.5.3 | [VERIFIED] |
| scikit-learn | 1.9.1 | [VERIFIED] |
| Neo4j | Not required for C1–C3 | [VERIFIED] |
| Aura `.env` | Missing | [OPEN] |

## 2. Commands

```powershell
.\.venv\Scripts\python.exe -m pytest rmi/tests -q
.\.venv\Scripts\python.exe -m compileall -q rmi
.\.venv\Scripts\python.exe -m rmi.train --keys 10000 --distribution uniform --seed 42
.\.venv\Scripts\python.exe -m rmi.benchmark --keys 10000 --queries 2000 --distribution uniform --seed 42 --repeats 3
```

## 3. C1 results

```text
python -m compileall -q rmi
(exit 0)

python -m pytest rmi/tests -q
29 passed
```

Manual core check:

```text
generate_sorted_keys(100) + RMIModel(bucket_count=8)
summary: key_count=100, bucket_count=8, stage1_error_buckets=1, max_stage2_error=3
lookup: 100 of 100 training keys found
```

Distribution/model matrix:

```text
uniform   ('linear', 'linear')   500/500 found
uniform   ('constant', 'constant') 500/500 found
uniform   ('linear', 'constant')   500/500 found
clustered ('linear', 'linear')   500/500 found
clustered ('constant', 'constant') 500/500 found
clustered ('linear', 'constant')   500/500 found
```

## 4. C2 benchmark results (synthetic, independent)

Uniform distribution, 10,000 keys, 2,000 queries, repeats=3:

```text
rmi_correct=2000, rmi_fallbacks=0, fallback_correct=2000
rmi_median_ns=4400, rmi_p95_ns=5700
fallback_median_ns=200, fallback_p95_ns=300
speedup=0.045
```

Clustered distribution, same size:

```text
rmi_correct=2000, rmi_fallbacks=0, fallback_correct=2000
rmi_median_ns=37600, rmi_p95_ns=84500
fallback_median_ns=200, fallback_p95_ns=300
speedup=0.005
```

Interpretation: the independent RMI is slower than the in-process `bisect` stand-in. That is a valid
negative result for this synthetic setup and is not the final Neo4j B+ tree comparison. The live comparison
belongs to C4 and is not claimed here.

## 5. Test coverage

| Area | Tests |
|---|---|
| Config parsing | Default two-stage config, env overrides, invalid bucket count, unknown model, non-two-stage rejection |
| Synthetic keys | Sorted/unique/length, determinism, invalid inputs, query sampling |
| RMI model | All training keys found, bounded candidate count, out-of-range fallback, unseen in-range fallback, bucket clamping, summary, fit validation |
| Training | Fitted model, idempotent retrain, CLI |

## 6. Not executed

- Benchmark versus live Neo4j B+ tree: C4, blocked by Person B PRs #8–#12 and Aura.
- Real exported key distribution: blocked by Person B merge.
- Docker Compose: not used by this lane.

## 7. Evidence policy

- Results are recorded from commands actually run.
- Synthetic results are labelled synthetic.
- Skips and blocked work are listed explicitly, not counted as passes.
