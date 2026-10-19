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
