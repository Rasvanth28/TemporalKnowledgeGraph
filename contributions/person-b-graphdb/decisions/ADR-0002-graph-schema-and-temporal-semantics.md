# ADR-0002 — Graph schema and temporal semantics

- **Status:** Accepted
- **Decision date:** 2026-10-19

## Context

Design document §2.3.2 defines four node types and six relationships, including
`(Article)-[:ABOUT]->(Topic)` and a pure chronological `(Event)-[:PRECEDES]->(Event)`.

Person A's actual output does not match those semantics exactly:

- `ExtractedEvent` carries a `Topic`; `ExtractionResult` does not carry an article topic.
- `Event.date_source` exists in `common/schema.py` but is absent from the design-doc property table.
- The pipeline does not produce `PRECEDES`; it produces only confidence-scored `EventLink` objects.
- The sample dataset has no event chains.

The graph lane must preserve the design document where possible without pretending the pipeline produced
data it did not. [VERIFIED from `common/schema.py`, `pipeline/extract.py`, `pipeline/link.py`, and design doc §2.3.2]

## Requirements and constraints

- Keep the four required indexes exactly as specified.
- Add uniqueness constraints for safe `MERGE` behavior.
- Support precise event-chain-by-topic queries.
- Preserve doc-literal `Article-ABOUT->Topic` if it does not compromise query correctness.
- Define chronological ordering deterministically, including same-date ties.
- Store `date_source`.
- Do not edit `common/schema.py`; the topic already lives on `ExtractedEvent`.
- Handle the `Topic.name` uniqueness-constraint backing index versus the required `topic_name` index.

## Alternatives considered

### ABOUT

1. **Article-only, derived from event topics.** Keeps the design doc literal, but a topic query returns
   every event in the article, including events on other topics.
2. **Event-only.** Precise, but removes the design-doc `Article-ABOUT` relationship.
3. **Both.** `Event-ABOUT->Topic` is canonical; `Article-ABOUT->Topic` is derived from the distinct topics
   of the article's events. Preserves the design doc and supports precise queries.

### PRECEDES

1. **Global chronological chain.** Sort all events by `(date, id)` and connect each event to its immediate
   successor. This is independent of `LINKED_TO`, matching the design doc's “pure chronological ordering”.
   It requires a rebuild after a batch because inserting an event changes its neighbours.
2. **Only `LINKED_TO` pairs.** Stable and local, but rejected because it makes `PRECEDES` dependent on
   semantic links, contradicting the design doc's definition.
3. **All pairs.** O(n²) edges; rejected.

### Same-date ordering

Sorting by `(date, id)` is deterministic, but the id tie-break is arbitrary. It must not be presented as a
real-world temporal ordering.

### Constraints and the Topic index

A uniqueness constraint creates its own backing index. On some Neo4j versions, an equivalent index already
exists when the required `topic_name` index is requested. The script must observe and document the actual
behavior rather than assume both named objects can coexist.

## Decision

### ABOUT

- Store `Topic` nodes for every event topic, including the `general` sentinel.
- Create `(Event)-[:ABOUT]->(Topic)` as the canonical event-topic edge.
- Derive `(Article)-[:ABOUT]->(Topic)` from the distinct topics of that article's events.
- Document that the `Event-ABOUT` edge extends design doc §2.3.2 and the `Article-ABOUT` edge is derived.
- Do not change `common/schema.py`; the topic is already on `ExtractedEvent`.

### PRECEDES

- Build a **global** chain: sort all `Event` nodes by `(date, id)` and connect each to its immediate
  successor.
- Same-date order is determined by id; this is an arbitrary deterministic tie-break, not a real ordering.
- Recompute after each write batch: delete stale `PRECEDES` relationships and recreate the chain in one
  transaction.
- Do not restrict `PRECEDES` to `LINKED_TO` pairs.

### Properties

- Store `Event.date_source` (`"explicit"` or `"inferred"`).
- Store `Article.date` and `Event.date` as native Neo4j `date` values.

### Indexes and constraints

Keep the four required indexes exactly as written in design doc §2.3.2. Add uniqueness constraints on:

- `Article.id`
- `Event.id`
- `Entity.id`
- `Topic.name`

The constraint backing indexes are additive and may satisfy a required index by equivalence. The schema
application script will verify the actual schema with `SHOW INDEXES` and report the observed result.

## Reasons

- Both `ABOUT` edges preserve the design-doc contract without sacrificing event-level topic precision.
- Global `PRECEDES` follows the design document's explicit definition and keeps chronology independent of
  semantic confidence.
- Native dates and the `event_date` index support Person C's range-lookup comparison.
- Uniqueness constraints make `MERGE` index-backed and prevent duplicates.
- Keeping `common/schema.py` unchanged avoids an unapproved cross-team contract change.

## Consequences and trade-offs

- The graph has redundant topic information (`Event-ABOUT` plus derived `Article-ABOUT`). The redundancy is
  intentional and documented.
- The `general` topic is stored and may be noisy in topic queries; consumers can filter it.
- Global `PRECEDES` rebuilds are O(n) and delete/recreate the relationship type after each batch. This is
  acceptable for the MVP but may need redesign at larger scale.
- Same-date `PRECEDES` edges imply a deterministic order, not a real one.
- The `topic_name` index may be observed as a constraint-owned equivalent rather than a separately named
  index. Reviewers must inspect `SHOW INDEXES`, not only the CQL text.

## Evidence

- Design doc §2.3.2 defines `Article-ABOUT->Topic` and `Event-PRECEDES->Event`. [VERIFIED]
- `common/schema.py` has `ExtractedEvent.topic` and `Event.date_source`; `ExtractionResult` has no topic. [VERIFIED]
- `pipeline/link.py` generates earlier → later links with same-date ordering by event id. [VERIFIED]
- `pipeline/extract.py` emits `Topic(name="general")` as a fallback. [VERIFIED]
- The four required index statements are quoted exactly in the design document. [VERIFIED]
- The actual Neo4j `SHOW INDEXES` outcome is not yet observed; it is a Stage 1 integration item. [OPEN QUESTION]

## Conditions to revisit

- The team decides that `PRECEDES` should be materialized only for related events.
- Global `PRECEDES` rebuilds become a performance problem.
- A date-precision field is added to `common/schema.py` to fix year-only dates.
- Neo4j reports a schema conflict that requires a different index/constraint order or naming strategy.
- Topic semantics change in Person A's output.
