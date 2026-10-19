# Project overview — Research/RMI lane

## 1. Problem statement

Neo4j answers date-key lookups with its B+ tree index. The project investigates whether a learned index — a
Recursive Model Index — can predict the position of a key directly and outperform the tree on the same
query set, while preserving correctness through bounded error search and a Neo4j fallback.

## 2. Objectives

1. Implement a config-driven two-stage RMI.
2. Bound every stage's training error and size a local correction window from it.
3. Guarantee correctness for training keys by construction.
4. Benchmark RMI lookup latency against an injectable fallback lookup on the same query set.
5. Implement an idempotent `retrain_rmi()` and measure update-drift before versus after retraining.
6. Wire the fallback to Person B's `graphdb/queries.py` once it is merged.
7. Record findings in `RESULTS.md`, including negative results.

## 3. Requirements

| ID | Requirement |
|---|---|
| C-R1 | Stage count and per-stage model types come from config, not hardcoded call sites. |
| C-R2 | Training keys are sorted, unique integers. |
| C-R3 | Every training key is found by bounded local search. |
| C-R4 | Out-of-range predictions report a fallback reason. |
| C-R5 | Benchmark RMI against the same query set as the fallback. |
| C-R6 | Retraining is idempotent and manually triggerable. |
| C-R7 | The drift experiment inserts keys outside the training range. |
| C-R8 | No shared Person A/Person B file is edited. |
| C-R9 | Live Neo4j integration is isolated behind an injected fallback. |
| C-R10 | Findings are documented with exact commands and observed results. |

## 4. Scope

### In scope

- `rmi/` package and `rmi/tests/`.
- Synthetic key generation, RMI training, error-bound lookup, benchmark harness, drift experiment.
- Contribution-local docs and ADRs.
- C4 wiring to Person B's query functions after B merges.

### Out of scope

- Custom low-level storage engines.
- Changing Person A's pipeline or Person B's graph code.
- A production scheduler; retraining is standalone and manually triggered for now.
- More than two RMI stages in the MVP.

## 5. Assumptions

- Person B will expose `events_in_date_range` and `event_by_id` as stable fallback functions. [VERIFIED from
  Person B's `feature/graphdb-queries` branch; not yet merged to `main`.]
- Person C can start against synthetic sorted keys, as stated in `PROJECT_PLAN.md`. [VERIFIED]
- `numpy` and `scikit-learn` are already pinned. [VERIFIED in `requirements.txt`]
- A real Neo4j benchmark requires Aura or Docker. [VERIFIED environment currently lacks both]

## 6. Constraints

- Branch from `main`, not from Person B branches.
- Touch only `rmi/` and `contributions/person-c-rmi/`.
- Do not edit `common/schema.py`, `pipeline/`, `scripts/`, `graphdb/`, root `README.md`, or
  `PROJECT_PLAN.md`.
- Do not add dependencies unless necessary; `numpy` and `scikit-learn` already exist.
- Live results must be labelled as observed; skips are not passes.

## 7. Terminology

| Term | Meaning |
|---|---|
| RMI | Recursive Model Index: staged models predicting key position. |
| Stage 1 | Model predicting a normalized position and therefore a bucket. |
| Stage 2 | Per-bucket model predicting a local position. |
| Error bound | Maximum training error, used to size the local search window. |
| Fallback | Correct lookup path used when RMI is out of range or unconfident. |
| Drift | New keys outside the training distribution/range after training. |
| `date_key` | Days since 1970-01-01, Person B's exported numeric event key. |

## 8. Acceptance criteria

C1 is accepted when:

- RMI core, config, synthetic keys, and training entry points exist.
- Every training key is found by bounded search for uniform and clustered distributions.
- Config-driven model choices still guarantee correctness.
- Unit tests pass; no shared file is modified.

C2 is accepted when:

- A benchmark harness compares RMI and an injected fallback on the same query set.
- Latency and correctness results are recorded, with live Neo4j deferred.
- Tests do not require Neo4j.

C3 is accepted when:

- `retrain_rmi()` is idempotent.
- The drift experiment measures before/after accuracy and latency on new out-of-range keys.
- `RESULTS.md` records the observed independent results.

C4 is accepted when:

- Person B's PRs are merged and `graphdb.queries` is on `main`.
- The fallback is wired to `events_in_date_range`/`event_by_id`.
- A live RMI-vs-B+tree benchmark runs against Aura and is recorded.

## 9. Dependencies

| Dependency | Needed for | Status |
|---|---|---|
| `numpy` | All RMI work | Installed |
| `scikit-learn` | Optional richer models later | Installed |
| Person B PRs #8–#12 | C4 only | Open, not merged |
| Aura `.env` | C4 live benchmark | Missing |
| Person B export | C4 real key distribution | Blocked by merge |
