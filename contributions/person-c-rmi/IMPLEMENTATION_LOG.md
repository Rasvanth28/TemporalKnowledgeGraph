# Implementation log — Research/RMI lane

Chronological record. Historical entries are not rewritten except to correct factual errors.

## 2026-10-19 — C1: two-stage RMI core

**Objective:** Scaffold the RMI lane, implement a config-driven two-stage RMI with error-bound correctness,
synthetic sorted keys, training entry points, and unit tests. Do not depend on Neo4j or Person B.

**Branch:** `feature/rmi-core`, created from `origin/main` (`b0d9f08`). Person B's PRs #8–#12 are open and
not merged; this branch does not include them.

**Files created:**

- `rmi/__init__.py`
- `rmi/config.py`
- `rmi/keys.py`
- `rmi/model.py`
- `rmi/train.py`
- `rmi/tests/__init__.py`
- `rmi/tests/conftest.py`
- `rmi/tests/test_config.py`
- `rmi/tests/test_keys.py`
- `rmi/tests/test_model.py`
- `rmi/tests/test_train.py`
- `contributions/person-c-rmi/` documentation scaffold
- `contributions/person-c-rmi/pr/PR-C1-rmi-core.md`

**Reasoning:** The plan allows synthetic sorted keys before the graph export exists. Stage 1 predicts a
normalized position and bucket; stage 2 predicts a local position per bucket. Each stage's maximum training
error sizes a bounded search window, so every training key is found without a full scan. Stage models and
bucket count are config-driven; a non-two-stage config fails clearly until the recursive extension is built.

**Alternatives considered:**

- Hardcoded linear two-stage model: rejected because the plan requires config-driven stage/model choices.
- Single-stage model: rejected as too inaccurate and non-representative of the research question.
- Importing Person B's query module now: rejected because it is not on `main` until #8–#12 merge.
- Binary search presented as the learned index: rejected as not a valid research result.

**Checks run and results:**

- `python -m compileall -q rmi` — exit 0. [VERIFIED]
- `pytest rmi/tests -q` — 29 passed. [VERIFIED]
- Manual core check — 100/100 training keys found. [VERIFIED]
- Additional distribution/model matrix — uniform and clustered keys found for
  `linear/linear`, `constant/constant`, and `linear/constant`. [VERIFIED]

**Results and failures:** C1 passes. The model is intentionally limited to two stages. No live Neo4j or
Person B dependency exists yet.

**Links:**

- [ADR-0001](decisions/ADR-0001-rmi-model-config-and-error-bounds.md)
- [TESTING.md](TESTING.md)
- [PR-C1](pr/PR-C1-rmi-core.md)

**Next:** C2 benchmark harness with an injected fallback, same query set for RMI and fallback, latency and
correctness results.

## 2026-10-19 — C2: benchmark harness with injected fallback

**Objective:** Measure RMI lookup latency against a correct fallback on the same query set, while keeping
the harness independent of Neo4j.

**Branch:** `feature/rmi-benchmark`, stacked on `feature/rmi-core` because PR C1 is not merged yet.

**Files created:**

- `rmi/fallback.py`
- `rmi/benchmark.py`
- `rmi/tests/test_benchmark.py`
- `contributions/person-c-rmi/pr/PR-C2-rmi-benchmark.md`

**Files modified:**

- `rmi/model.py` — added scalar model prediction to remove numpy array allocation from the hot lookup path.
- `contributions/person-c-rmi/README.md`
- `contributions/person-c-rmi/ARCHITECTURE.md`
- `contributions/person-c-rmi/IMPLEMENTATION_LOG.md`
- `contributions/person-c-rmi/TESTING.md`
- `contributions/person-c-rmi/REVIEW_GUIDE.md`
- `contributions/person-c-rmi/RESULTS.md`
- `contributions/person-c-rmi/SESSION_HANDOFF.md`
- `contributions/person-c-rmi/PROPOSED_ROOT_README_SECTION.md`

**Reasoning:** `benchmark_lookup` accepts any `FallbackLookup` callable, so C4 can inject the Neo4j
adapter without changing the measurement logic. The independent benchmark uses `bisect` as a correct local
stand-in; it is not a B+ tree measurement. The first benchmark run exposed Python/numpy scalar overhead, so
`LinearModel` and `ConstantModel` gained `predict_scalar`, and `RMIModel.lookup` now uses it.

**Alternatives considered:**

- Import `graphdb.queries` now: rejected because it is not on `main`.
- Print only RMI timings without a fallback: rejected because the research question is comparative.
- Present the binary-search fallback as the B+ tree result: rejected; it is labelled a stand-in.

**Checks run and results:**

- `python -m compileall -q rmi` — exit 0. [VERIFIED]
- `pytest rmi/tests -q` — 35 passed. [VERIFIED]
- Uniform, 10,000 keys / 2,000 queries / repeats=3:
  `rmi_correct=2000`, `rmi_fallbacks=0`, `fallback_correct=2000`,
  `rmi_median_ns=4400`, `fallback_median_ns=200`, `speedup=0.045`. [VERIFIED]
- Clustered, same size:
  `rmi_correct=2000`, `rmi_fallbacks=0`, `fallback_correct=2000`,
  `rmi_median_ns=37600`, `fallback_median_ns=200`, `speedup=0.005`. [VERIFIED]
- Live Neo4j versus B+ tree: not executed. [NOT EXECUTED]

**Results and failures:** The independent synthetic benchmark currently reports the RMI as slower than a
local `bisect` fallback, especially for clustered keys. That is a valid independent finding, but it is not
the final Neo4j comparison: `bisect` is in-process C code, while the real fallback is a Neo4j round trip.
The result is recorded honestly in [RESULTS.md](RESULTS.md).

**Links:**

- [ADR-0002](decisions/ADR-0002-fallback-benchmark-contract.md)
- [TESTING.md](TESTING.md)
- [RESULTS.md](RESULTS.md)
- [PR-C2](pr/PR-C2-rmi-benchmark.md)

**Next:** C3 update-drift experiment, idempotent retraining metrics, and `RESULTS.md` update.

## 2026-10-19 — C3: update-drift experiment

**Objective:** Measure lookup accuracy and latency before and after a single manually triggered retrain
when new keys arrive outside the trained range.

**Branch:** `feature/rmi-drift`, stacked on `feature/rmi-benchmark` because PR C2 is not merged yet.

**Files created:**

- `rmi/drift.py`
- `rmi/tests/test_drift.py`
- `contributions/person-c-rmi/pr/PR-C3-rmi-drift.md`

**Files modified:**

- `contributions/person-c-rmi/README.md`
- `contributions/person-c-rmi/ARCHITECTURE.md`
- `contributions/person-c-rmi/IMPLEMENTATION_LOG.md`
- `contributions/person-c-rmi/TESTING.md`
- `contributions/person-c-rmi/REVIEW_GUIDE.md`
- `contributions/person-c-rmi/RESULTS.md`
- `contributions/person-c-rmi/SESSION_HANDOFF.md`
- `contributions/person-c-rmi/PROPOSED_ROOT_README_SECTION.md`

**Reasoning:** The experiment shifts new keys above the initial maximum, so every query is out of range
before retraining. It measures the same query set before and after `retrain_rmi()`. This directly answers
the design document's update-drift question without Neo4j. The retrain function is the existing idempotent
`retrain_rmi` from C1.

**Alternatives considered:**

- Retrain on every insert: rejected; expensive and out of MVP scope.
- Wait for live Neo4j: rejected; the drift question can be answered synthetically now.
- Incremental model updates: deferred to backlog.

**Checks run and results:**

- `python -m compileall -q rmi` — exit 0. [VERIFIED]
- `pytest rmi/tests -q` — 39 passed. [VERIFIED]
- Uniform drift, initial=5,000, new=500, queries=500, repeats=3:
  before correct 0 / fallbacks 500; after correct 500 / fallbacks 0; retrain 3.8 ms. [VERIFIED]
- Clustered drift, same size:
  before correct 0 / fallbacks 500; after correct 500 / fallbacks 0; retrain 4.9 ms. [VERIFIED]

**Results and failures:** One retrain recovered every out-of-range query in the synthetic experiment.
Clustered keys remain slower to answer after retraining, which is a real limitation of the current model,
not a correctness failure.

**Links:**

- [ADR-0003](decisions/ADR-0003-retrain-drift-experiment.md)
- [TESTING.md](TESTING.md)
- [RESULTS.md](RESULTS.md)
- [PR-C3](pr/PR-C3-rmi-drift.md)

**Next:** C4 is blocked until Person B PRs #8–#12 merge and Aura `.env` exists. After that: wire the real
`graphdb.queries` fallback, run the live RMI-vs-B+tree benchmark, and finalize `RESULTS.md`.
