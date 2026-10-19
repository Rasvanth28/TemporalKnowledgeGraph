# ADR-0003 — Idempotent write and validation semantics

- **Status:** Accepted
- **Decision date:** 2026-10-19

## Context

The writer must consume `PipelineOutput` repeatedly without creating duplicate nodes or relationships.
It must also handle malformed links and relationship updates deterministically.

The pipeline emits `LINKED_TO` links with confidence and reason. A later run with a different corpus can
produce a different score or reason for the same `(from_event_id, to_event_id)` pair, or omit a pair that
was present earlier. The design document does not specify the re-run policy.

`PRECEDES` is not produced by the pipeline and must be derived. Its global chain changes when a new event
is inserted between existing dates.

## Requirements and constraints

- `MERGE` on stable ids.
- Parameterized Cypher only.
- Batch with `UNWIND` inside explicit transactions.
- Return created/matched counts so idempotency is measurable.
- Re-running identical input must leave identical counts.
- Validate link endpoints against both the current batch and existing graph events.
- On missing endpoints, fail the whole transaction, roll back, and raise a clear validation error listing
  the missing ids.
- Latest input wins for `LINKED_TO` confidence and reason.
- Do not delete stale links by default.
- Rebuild global `PRECEDES` idempotently after each write batch, in one transaction.
- Never wipe the database.

## Alternatives considered

### `LINKED_TO` re-run

1. **Create-only.** Keeps the first observed score forever. Simple, but stale and wrong after a corpus
   change or a scoring fix.
2. **Latest input wins.** `ON MATCH SET` updates `confidence` and `reason`. The graph reflects the current
   pipeline output.
3. **Highest confidence wins.** Monotonic, but a lower-confidence newer judgment can never correct an old
   one; reason strings also become inconsistent.

### Stale link deletion

1. **Delete links absent from the new batch.** Produces a clean corpus snapshot, but risks deleting links
   that an incremental batch simply did not include.
2. **Do not delete by default.** Safer for incremental writes; old links may remain. This is the chosen
   MVP behavior and a documented limitation/backlog item.

### Missing link endpoints

1. **Skip and report.** Keeps the batch going, but hides a pipeline or input bug and can silently lose
   relationships.
2. **Fail and roll back.** Makes corruption visible; the caller must fix the data or the batch boundaries.
   This is the chosen behavior.

### `PRECEDES` derivation

1. **Only linked pairs.** Rejected in ADR-0002 because it contradicts pure chronology.
2. **Global rebuild after each batch.** Delete stale `PRECEDES` and recreate the chain in `(date, id)` order
   in one transaction. Deterministic and idempotent.

## Decision

- Use `MERGE` on `Article.id`, `Event.id`, `Entity.id`, and `Topic.name`.
- Use `ON CREATE SET` for all node/relationship properties.
- For `LINKED_TO`, also use `ON MATCH SET` for `confidence` and `reason`, so the latest input wins.
- Do not delete `LINKED_TO` links absent from a later batch. Record this as a known limitation and backlog
  item.
- Validate every `LINKED_TO` endpoint against the union of:
  - event ids in the current batch, and
  - event ids already present in Neo4j.
- If any endpoint is missing, raise a validation error listing the missing ids and roll back the whole
  transaction.
- After the node/relationship batch, rebuild global `PRECEDES`:
  1. delete stale `PRECEDES` relationships in the transaction;
  2. sort all `Event` nodes by `(date, id)`;
  3. connect each event to its immediate successor with `MERGE`.
- Return counts for nodes and relationships created versus matched.
- Deduplicate repeated `(from, to)` pairs deterministically within a payload; document the rule in code and
  tests.

## Reasons

- Latest-input-wins keeps `LINKED_TO` aligned with the current pipeline, including scoring fixes.
- Not deleting stale links avoids accidental loss during incremental writes.
- Failing on missing endpoints surfaces data bugs instead of producing a partially correct graph.
- A global `PRECEDES` rebuild is simple, deterministic, and testable for the MVP.
- Counts make idempotency measurable rather than asserted.

## Consequences and trade-offs

- A later run with a narrower corpus leaves old `LINKED_TO` edges behind.
- Global `PRECEDES` rebuilds delete and recreate all `PRECEDES` edges after each batch; this will not scale
  indefinitely without redesign.
- Failing the whole transaction means one bad link blocks the batch, which is intentional for correctness.
- If the writer processes a partial batch that references existing events, endpoint validation must query
  the database and cannot rely only on the payload.

## Evidence

- `pipeline/export.py` writes `PipelineOutput` as nested JSON with ISO date strings. [VERIFIED]
- `pipeline/link.py` produces links with `from_event_id`, `to_event_id`, `confidence`, and `reason`. [VERIFIED]
- The design doc requires idempotent `MERGE` writes but does not define re-run update or stale-link policy. [VERIFIED]
- The owner explicitly selected latest-input-wins, fail-and-rollback, and global `PRECEDES` recomputation. [VERIFIED from conversation]
- The idempotency and out-of-order insertion tests are Stage 2 deliverables, not yet executed. [OPEN QUESTION]

## Conditions to revisit

- Stale-link cleanup becomes required for correctness or a demo.
- Global `PRECEDES` rebuilds become too slow or contend with concurrent writes.
- The writer starts processing very large batches and needs per-article transaction boundaries.
- Duplicate `(from, to)` pairs occur in real pipeline output and the chosen dedupe rule proves unsuitable.
