# ADR-0003 — Idempotent retraining and update-drift experiment

- **Status:** Accepted
- **Decision date:** 2026-10-19

## Context

The design document's central open question is update drift: new events arrive continuously, while a
learned index reflects its training snapshot. The plan requires a standalone, idempotent `retrain_rmi()`
and an experiment that inserts new events outside the training range, then measures accuracy and latency
before and after one manually triggered retrain.

## Requirements and constraints

- Retraining must be manually triggerable and idempotent.
- No production scheduler in the MVP.
- The experiment must use new keys outside the training range.
- Results must be recorded honestly, including unchanged or worse results.
- No Neo4j dependency in C3.

## Alternatives considered

1. **Retrain on every insert.** Rejected: expensive and defeats the purpose of a learned index.
2. **Do nothing until the final integration.** Rejected: the drift question can be answered synthetically.
3. **Idempotent full retrain plus an out-of-range batch experiment.** Chosen.
4. **Incremental model update.** Deferred; not required for the MVP.

## Decision

- `retrain_rmi(keys, config)` fits a fresh model from the current key set. The same keys and config produce
  an equivalent model.
- The drift experiment:
  1. trains on an initial key range;
  2. inserts a batch of new keys outside that range;
  3. measures query accuracy and latency before retraining;
  4. calls `retrain_rmi()` once;
  5. repeats the same query set and reports before/after.
- Results are written to `contributions/person-c-rmi/RESULTS.md`; root `RESULTS.md` is proposed later.

## Reasons

- Answers the design document's open question without waiting for Neo4j.
- Idempotent full retraining is simple and testable.
- Manual triggering matches the Week-1 scope and can later be wired to a scheduler.

## Consequences and trade-offs

- Synthetic drift is not identical to real news-event drift.
- Full retraining cost is not optimized in the MVP.
- The experiment measures exact-key lookup, not full graph queries.

## Evidence

- `PROJECT_PLAN.md` requires a standalone `retrain_rmi()` and the update-drift experiment. [VERIFIED]
- The design document names update drift as the central open question. [VERIFIED]
- C3 tests and RESULTS draft will record observed synthetic results. [PLANNED]

## Conditions to revisit

- A real scheduler is introduced.
- Incremental or partial retraining is required.
- Real exported keys change the drift conclusions.
