# ADR-0004 — Query, API, and export contracts

- **Status:** Accepted
- **Decision date:** 2026-10-19

## Context

Person C depends on `graphdb/queries.py` as the Neo4j fallback for date-key lookups. A future frontend may
consume the API. Changing query names, parameters, return shapes, or export columns later would break those
consumers.

The design document permits Cypher/Postman before a UI, but the project plan recommends a thin FastAPI
layer. The pipeline has no Guardian-independent chain data, so end-to-end chain tests need a synthetic
fixture.

## Requirements and constraints

- Query functions have explicit typed signatures and return plain dicts/dataclasses, not driver objects.
- Chain queries support `min_confidence`, a hard depth cap, a result limit, and chronological ordering.
- Return confidence and reason on every traversed edge.
- Provide `events_in_date_range(start, end)` and `event_by_id(id)` as RMI fallback targets.
- Entity-name matching must be consistent with Person A's normalization and must keep the `entity_name`
  index usable.
- Do not import spaCy-dependent pipeline modules into `graphdb/`.
- API routes call `queries.py`; no business logic in handlers.
- API uses Pydantic response models, validation, sensible error codes, `/health`, and OpenAPI docs.
- Provide curl examples and a Postman collection.
- Flat export keeps the existing event-key column contract.
- Tests must not require Guardian or a Guardian API key.
- Stable contracts require review from the consuming lane when changed.

## Alternatives considered

### Entity matching

1. **Exact normalized, case-sensitive.** Uses `Entity.name` and the `entity_name` index. Requires query input
   to be normalized the same way as Person A's entity names.
2. **Case-insensitive `toLower(n.name)`.** Convenient, but a normal property index cannot serve the
   comparison; it becomes a scan unless a new normalized property/index is added.
3. **Add a lowercase `name_key` property and index.** Fast case-insensitive lookup, but adds a schema/index
   object beyond the approved four indexes and requires writer changes.

### API shape

1. **Postman-only.** Allowed by the design doc and cheapest, but not a stable programmatic contract and not
   useful to a future frontend without rework.
2. **FastAPI plus Postman/curl.** More implementation and tests, but a documented, typed contract and
   automatic OpenAPI.
3. **Direct Cypher only.** Acceptable for exploration, not for a consumer contract.

### End-to-end test data

1. **Official sample only.** No event chains, so traversal is not exercised.
2. **Guardian data.** Requires a key and network; not reproducible for reviewers.
3. **Synthetic test-only fixture.** Reproducible, no Guardian content, no spaCy dependency for the fixture
   shape, and can be engineered to exercise chains.

### Flat export

1. **Reuse the pipeline CSV only.** Cannot prove the graph is populated or export from the graph.
2. **Export from Neo4j with the same columns.** Proves the graph round-trip and preserves Person C's
   contract.
3. **Invent new columns.** Rejected; would break Person C.

## Decision

### Query contract

- Expose typed functions in `graphdb/queries.py` returning plain Python dicts/dataclasses.
- Implement entity, date-range, and topic chain queries with:
  - `min_confidence`
  - hard depth cap
  - result limit
  - chronological ordering
  - confidence and reason on every edge.
- Provide `events_in_date_range(start, end)` and `event_by_id(id)` as stable fallback functions.
- Entity matching is exact and case-sensitive after mirroring Person A's normalization:
  whitespace collapse, leading `"the"` removal, trailing possessive removal.
- Implement and test the normalizer inside `graphdb/` rather than importing `pipeline.extract`.
- An optional case-insensitive fallback may run only when the exact match returns nothing. It must be
  clearly documented and marked in code as a non-indexed scan.

### API

- Use FastAPI with Pydantic response models.
- Routes call `queries.py`; no graph logic in route handlers.
- Include `/health`, input validation, sensible HTTP error codes, and automatic OpenAPI docs.
- Configuration comes from the same environment variables as the rest of the backend.
- Provide curl examples and a Postman collection.
- Propose endpoint paths and response models for owner review in Stage 4 Phase B before implementation.

### Flat export

- Export from the populated Neo4j graph, not by re-reading the pipeline JSON.
- Keep the columns:

```text
event_id, date_key, date, date_source, type, article_id
```

- Keep `date_key` as days since `1970-01-01`.
- Sort by `(date_key, event_id)`.
- Do not duplicate the pipeline CSV blindly; the graph export must be generated from graph data and tested
  against the same column contract.

### Test data

- Add a synthetic, clearly labeled test-only fixture under `graphdb/tests/fixtures/`.
- Make it `pipeline_output.json`-shaped with 3–4 event chains.
- Use original text only; no Guardian content.
- Do not require a Guardian API key anywhere.
- Also run the official three-article sample through `scripts/run_pipeline.py` and the writer as a
  no-regression/count check.

### Stable-contract rule

Changing the names, parameters, return shapes, or meanings of `queries.py` functions or API endpoints
requires a PR reviewed by the consuming lane (Person C for fallback/export, frontend owner if applicable).

## Reasons

- Exact normalized matching keeps the required `entity_name` index useful and avoids schema creep.
- FastAPI gives a typed contract that a frontend and Person C can rely on.
- The synthetic fixture makes chain tests reproducible without Guardian or spaCy.
- Graph-sourced export proves the populated graph and preserves Person C's existing contract.

## Consequences and trade-offs

- Entity lookup is case-sensitive; users must use the normalized case. The fallback may be slower and is
  explicitly non-indexed.
- FastAPI adds dependencies and test surface, which the project plan already recommends.
- The synthetic fixture is not real news data; it tests contract mechanics, not NLP quality.
- The official sample will not exercise `LINKED_TO` chains; that is a known dataset limitation.
- API endpoints are not yet fixed; consumers must wait for Stage 4 Phase B.

## Evidence

- `pipeline/extract.py` normalizes whitespace, a leading `"the"`, and a trailing possessive, but preserves
  case. [VERIFIED]
- `pipeline/export.py` defines the existing six-column contract and days-since-epoch `date_key`. [VERIFIED]
- Design doc §2.1 permits Cypher/Postman before a UI. [VERIFIED]
- The official sample has three articles and no event chains, per the root README. [VERIFIED]
- No query/API/export code exists yet; this ADR sets direction, not observed behavior. [PROPOSED for implementation]

## Conditions to revisit

- Person C requires case-insensitive entity lookup as a stable contract.
- API consumers need different response shapes or additional query dimensions.
- Person A adds date precision or changes normalization.
- The graph export needs columns beyond the existing six.
- The team decides a real frontend replaces the Postman/curl contract.
