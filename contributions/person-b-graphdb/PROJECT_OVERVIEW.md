# Project overview — Graph DB & Backend lane

## 1. Problem statement

The NLP pipeline produces article-level extraction results: each article mentions entities and describes
events, each event involves entities and has a topic, and the linker proposes confidence-scored links
between events. Those results are not yet persisted in a graph, cannot be traversed as event chains, and
are not exposed through a stable backend contract.

The Graph DB & Backend lane must:

- persist the pipeline output in Neo4j without duplicating nodes on re-runs;
- preserve the design document's graph model;
- expose query paths for entity, date range, and topic;
- give Person C a reliable Neo4j fallback and a flat event-key export;
- give a future frontend a stable API rather than requiring direct Cypher.

## 2. Objectives

1. Stand up Neo4j through Aura free (working instance) with Docker Compose as a documented alternative.
2. Implement the four indexes from design doc §2.3.2 exactly, plus approved uniqueness constraints.
3. Write `graphdb/writer.py` as an idempotent, `MERGE`-based, parameterized writer over `PipelineOutput`.
4. Write `graphdb/queries.py` as a stable query contract for entity/date/topic chains and flat lookups.
5. Write `graphdb/api.py` as a thin FastAPI layer over `queries.py`.
6. Export a flat event-key dataset from the populated graph for Person C.
7. Test unit behavior with mocked drivers and integration behavior with a real Neo4j instance.
8. Document setup, contracts, limitations, and evidence.

## 3. Requirements

### Functional

| ID | Requirement |
|---|---|
| F1 | Store `Article`, `Event`, `Entity`, and `Topic` nodes from `PipelineOutput`. |
| F2 | Store `DESCRIBES`, `MENTIONS`, `ABOUT`, `INVOLVES`, `PRECEDES`, and `LINKED_TO`. |
| F3 | Re-running the writer on identical input leaves identical node and relationship counts. |
| F4 | `LINKED_TO` carries `confidence` and `reason`; latest input wins on re-run. |
| F5 | Event dates are native Neo4j `date` values so the `event_date` index supports range lookup. |
| F6 | Query by entity name, date range, and topic; return chronological event chains. |
| F7 | Provide `events_in_date_range(start, end)` and `event_by_id(id)` for Person C's fallback path. |
| F8 | Expose the queries through a documented FastAPI contract with `/health` and OpenAPI docs. |
| F9 | Export `event_id, date_key, date, date_source, type, article_id` from the graph. |
| F10 | Integration tests use only `test_`-prefixed ids and delete only those exact nodes. |

### Non-functional

| ID | Requirement |
|---|---|
| N1 | Parameterized Cypher only; no string interpolation of data values. |
| N2 | No hardcoded credentials, URIs, or secrets. |
| N3 | Small driver/session wrapper so tests can mock Neo4j. |
| N4 | Integration tests auto-skip when `NEO4J_URI` is unset. |
| N5 | No database wipe, ever; Aura free has one database. |
| N6 | Documentation and code must label unverified claims honestly. |
| N7 | Shared-file changes are limited to the approved Stage 1 list. |

## 4. Scope

### In scope

- Neo4j schema, indexes, constraints, connection wrapper, health check.
- Schema application script that is idempotent and rerunnable.
- Writer for the complete pipeline output.
- Query functions and API.
- Graph-to-flat export.
- Unit and integration tests, including the official sample no-regression run.
- Contribution-local documentation and ADRs.

### Out of scope for this lane

- Changes to Person A's extraction, linking, or `common/schema.py`.
- Changes to Person C's RMI implementation.
- A polished frontend.
- Deleting or reconciling stale links from earlier corpora.
- Repairing the year-only date limitation in the pipeline.
- Deployment beyond a local/Aura development instance.

## 5. Assumptions

- Person A's `PipelineOutput` JSON contains `results` and `links`, with ISO date strings. [VERIFIED from `pipeline/export.py`]
- Event links already point earlier → later, with same-date ties broken by event id. [VERIFIED from `pipeline/link.py`]
- The design document permits Cypher/Postman as the first interface before a UI. [VERIFIED from design doc §2.1]
- Aura free provides one database for this project. [ASSUMPTION from the project brief]
- Docker is not available in the current shell; Compose cannot be executed here. [VERIFIED]
- Person A's sample dataset has no event chains; real chains came from Guardian fetches. [VERIFIED from README]

## 6. Constraints

- `main` is protected by team policy; work goes through reviewed PRs. [ASSUMPTION; GitHub protection not directly inspected]
- Never commit `.env`, passwords, or fetched Guardian bodies.
- Do not edit Person A's files or shared docs without explicit approval.
- The four index statements must remain exactly as specified in design doc §2.3.2.
- Uniqueness constraints are additions, not replacements for the four indexes.
- `PRECEDES` is global, recomputed after each write batch, not restricted to `LINKED_TO` pairs.
- Entity-name matching is exact and case-sensitive after Person A-compatible normalization; the index must remain usable.

## 7. Terminology

| Term | Meaning |
|---|---|
| `PipelineOutput` | `common.schema.PipelineOutput`: extraction results plus corpus-level event links. |
| `ExtractedEvent` | One event with its involved entities and one topic. |
| `LINKED_TO` | Confidence-scored semantic relation between two events. |
| `PRECEDES` | Pure chronological successor relation between adjacent events in global `(date, id)` order. |
| `date_source` | `"explicit"` when the event date was stated, `"inferred"` when inherited from the article. |
| `date_key` | Days since 1970-01-01, used by Person C's RMI. |
| Stable contract | A public function/API shape whose change requires review from the consuming lane. |

## 8. Acceptance criteria

Stage 0 is accepted when:

- The contribution folder contains every documented file and all relative links resolve.
- ADRs exist with `Accepted` status, decision date `2026-10-19`.
- No shared tracked file is modified.
- The local OpenCode config points at `contributions/person-b-graphdb/AGENTS.md` and is excluded locally.
- `SESSION_HANDOFF.md` records the exact stopping point.

Stage 1 is accepted when:

- Four indexes and four constraints are defined in CQL exactly as approved.
- `python -m graphdb.health` works against a reachable instance and fails clearly otherwise.
- `python -m graphdb.apply_schema` is rerunnable and reports the observed `Topic.name` index/constraint interaction.
- Unit tests pass with mocks; existing Person A tests still pass.
- Integration tests run when `NEO4J_URI` is present and skip cleanly otherwise.
- Docker Compose is present and explicitly marked untested if not executed.
- No secrets are printed or committed.

Stages 2–6 acceptance criteria are added when those stages begin.

## 9. Dependencies

### Existing, reused

- `common/schema.py` — shared dataclasses; no edits planned.
- `pipeline/export.py` — existing flat export contract.
- `pipeline/link.py` — link direction/deterministic ordering.
- `pipeline/extract.py` — entity normalization behavior to mirror.
- `data/sample_articles.json` — official no-regression sample.
- `pytest`, `python-dotenv`, Pydantic, HTTPX (already in `requirements.txt`).

### New, approved for Stage 1

- Neo4j Python driver.
- FastAPI and Uvicorn.
- New transitive pins only as actually installed and tested.
- No new dependency outside `.venv`.

## 10. Open issues

- Aura instance availability and the exact observed schema-object interaction.
- OpenCode runtime version confirmation; fallback is the documented per-session instruction.
- Whether stale-link cleanup becomes a backlog item or a later writer mode.
- API endpoint/response-model details remain for Stage 4 Phase B.
