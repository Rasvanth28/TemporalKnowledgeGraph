# ADR-0001 — Two-stage RMI, config-driven stages, error-bound correctness

- **Status:** Accepted
- **Decision date:** 2026-10-19

## Context

The research question is whether a learned index can beat Neo4j's B+ tree for date-key lookups. The MVP
must be simple, explainable, and correct enough to benchmark honestly.

`PROJECT_PLAN.md` requires a simple 2-stage RMI, stage count/model type read from config, and a correction
window sized from each stage-2 model's maximum training error.

## Requirements and constraints

- Stage count and per-stage model type must come from config.
- Sorted, unique integer keys.
- Every training key must be found without a full scan.
- Out-of-range keys must report fallback, not return a wrong answer.
- No Neo4j dependency in C1.

## Alternatives considered

1. **Single-stage linear model.** Simpler, but too inaccurate for large ranges and does not match the plan's
   2-stage RMI.
2. **Hardcoded two-stage linear model.** Easy, but violates the config-driven requirement and blocks richer
   model experiments.
3. **Binary search as the "learned" index.** Correct and fast, but not a learned index and not a valid
   research result.
4. **Two-stage RMI with config-driven models and error windows.** Chosen.

## Decision

Implement a two-stage RMI:

- Stage 1 predicts a normalized global position, converted to a bucket.
- A per-bucket stage-2 model predicts a local position.
- Each stage's maximum training absolute error sizes a bounded search window.
- Lookup searches candidate buckets within the stage-1 error bound and local positions within the stage-2
  window.
- `RMIConfig(stage_models=(...), bucket_count=...)` drives model choices; a non-two-stage config raises a
  clear `RmiConfigError` until the recursive extension is built.

Supported model names for the MVP: `linear` and `constant`.

## Reasons

- Matches the plan's RMI structure and keeps the implementation explainable.
- Config-driven model choices allow constant-vs-linear comparisons without code changes.
- Error-window lookup gives a testable correctness guarantee.
- Out-of-range fallback is explicit for the later Neo4j path.

## Consequences and trade-offs

- Only two stages are implemented; more stages require a later recursive design.
- Error windows can become large for weak models (for example, constant stage 1), trading speed for
  correctness.
- Correctness is guaranteed on training keys; unseen keys inside the range may report `not_found` fallback.
- Synthetic keys are not the real event-key distribution.

## Evidence

- `rmi/tests/test_model.py` verifies every training key is found for uniform and clustered keys and for
  linear/constant model combinations.
- `rmi/tests/test_config.py` verifies env/config parsing and clear rejection of a three-stage config.
- [TESTING.md](../TESTING.md) records the exact commands and results.

## Conditions to revisit

- Real exported keys show a distribution where two stages are insufficient.
- More than two stages are needed.
- A richer per-stage model is added.
- Benchmarks show the search window dominates latency.
