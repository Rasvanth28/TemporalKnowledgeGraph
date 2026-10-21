# Person B — Graph DB & Backend contribution

- **Owner:** Person B (Graph DB & Backend lane)
- **Contribution id:** `person-b-graphdb`
- **Branch:** `feature/graphdb-export-e2e`
- **Current stage:** Stages 0–6 implemented and unit-tested; five stacked PRs are open (#8–#12). Live Aura
  verification and Docker Compose execution are still pending.

> This folder is the isolated documentation home for the Graph DB & Backend lane. Code for the lane lives
> in `graphdb/`. Shared project files are not edited from this folder unless the owner explicitly approves
> a specific change.

## Purpose

The lane turns Person A's NLP pipeline output into a queryable temporal knowledge graph in Neo4j and
exposes a small, stable backend contract for consumers:

- Person C's RMI research lane, which needs a Neo4j fallback path and a flat event-key dataset.
- A future frontend or Postman/curl client, which needs stable query endpoints.

## Problem and scope

News articles are processed independently by the ML/NLP pipeline. The graph lane must connect them:

1. Store `Article`, `Event`, `Entity`, and `Topic` nodes.
2. Store `DESCRIBES`, `MENTIONS`, `ABOUT`, `INVOLVES`, `PRECEDES`, and `LINKED_TO` relationships.
3. Keep writes idempotent so re-processing does not duplicate nodes or relationships.
4. Answer event-chain queries by entity, date range, and topic.
5. Expose those queries through a stable, documented API contract.
6. Export a flat event-key dataset from the populated graph for Person C.
7. Prove the path with unit tests, a mocked-driver test suite, and a real Neo4j integration test.

Stage 0 does not implement any of the runtime behavior above; it creates the documentation, decisions,
and local workflow needed to build it without drifting into shared files.

## Implemented functionality and status

| Area | Status | Notes |
|---|---|---|
| Contribution scaffold | **Complete** | This folder and the ADR/decision records |
| Local OpenCode workflow | **Complete** | Local untracked `opencode.json`; no root `AGENTS.md` |
| Neo4j config, connection, health | **Stage 1 implemented** | Environment-only config, mockable wrapper, `python -m graphdb.health` |
| Neo4j Aura instance | **Pending** | Owner creates it and fills the local `.env`; credentials never enter chat or git |
| Docker Compose alternative | **Implemented, untested** | Docker is not available in the current shell |
| Schema, indexes, constraints | **Stage 1 implemented; Aura pending** | Four design-doc indexes plus four uniqueness constraints, verified with mocks; live `SHOW INDEXES` pending |
| `graphdb/apply_schema.py` | **Stage 1 implemented** | Rerunnable, equivalent-index handling, `--verify-only` |
| `graphdb/writer.py` | **Stage 2 implemented; Aura pending** | Idempotent `MERGE`/`UNWIND`, endpoint validation, counts, latest-input-wins `LINKED_TO`, global `PRECEDES` rebuild |
| Synthetic writer fixture | **Stage 2 implemented** | `graphdb/tests/fixtures/pipeline_output.json`; original test-only text, no spaCy or Guardian dependency |
| `graphdb/queries.py` | **Stage 3 implemented; Aura pending** | Entity/date/topic chains, flat lookup helpers, depth/limit/confidence guards, chronological ordering |
| `graphdb/normalize.py` | **Stage 3 implemented** | Backend copy of Person A's entity-name normalization; no spaCy import |
| `graphdb/api.py` | **Stage 4 implemented; Aura pending** | FastAPI, Pydantic models, OpenAPI, health, query routes |
| API contract and clients | **Stage 4 implemented** | `contributions/person-b-graphdb/api/` with contract, curl examples, and Postman collection |
| Graph-to-flat export | **Stage 5 implemented; Aura pending** | Same columns and `date_key` contract as `pipeline/export.py` |
| End-to-end round-trip | **Stage 6 prepared; Aura pending** | Synthetic fixture tests plus official sample no-regression test, both skipped without `NEO4J_URI` |

## Main files changed

Stages 0–6:

- `contributions/person-b-graphdb/` — this documentation set, API contract/clients, PR descriptions, and
  final audit.
- `graphdb/` — config, connection wrapper, health check, schema application, writer, queries, normalizer,
  API, export, CQL files, tests.
- `requirements.txt` — six new installed/tested pins appended.
- `.env.example` — Neo4j placeholders appended.
- `docker-compose.yml` — local alternative, untested here.
- `opencode.json` — local, untracked, excluded through `.git/info/exclude`.
- `.git/info/exclude` — local-only exclusion line; not a shared repository file.

No root README, `PROJECT_PLAN.md`, `Documentation/`, `common/schema.py`, `pipeline/`, or `scripts/` file
was changed. [VERIFIED]

## How to run or reproduce

The Stage 1 commands are executable inside `.venv`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m graphdb.health
python -m graphdb.apply_schema
python -m graphdb.writer --input data/exports/pipeline_output.json
python -m graphdb.api
python -m graphdb.export --output data/exports/graph_event_keys.csv
python -m pytest
```

Neo4j connection settings come from environment variables loaded from `.env`:

```text
NEO4J_URI
NEO4J_USER
NEO4J_PASSWORD
NEO4J_DATABASE
```

`.env.example` contains placeholders only. `.env` is git-ignored and must never be committed or
printed. [VERIFIED]

## Documentation map

- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) — problem, requirements, scope, assumptions, acceptance criteria.
- [ARCHITECTURE.md](ARCHITECTURE.md) — components, interfaces, data flow, Cypher model.
- [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) — chronological implementation record.
- [TESTING.md](TESTING.md) — environment, commands, actual results, gaps.
- [REVIEW_GUIDE.md](REVIEW_GUIDE.md) — recommended review order and end-to-end trace.
- [AGENTS.md](AGENTS.md) — persistent workflow rules for this lane's OpenCode sessions.
- [SESSION_HANDOFF.md](SESSION_HANDOFF.md) — current status and next step; rewritten at session end.
- [PROPOSED_ROOT_README_SECTION.md](PROPOSED_ROOT_README_SECTION.md) — text for the eventual root README section.
- [decisions/README.md](decisions/README.md) — ADR index and template.
- [diagrams/architecture.md](diagrams/architecture.md) — Mermaid architecture diagram.
- [api/API_CONTRACT.md](api/API_CONTRACT.md) — stable HTTP contract, models, limits, and errors.
- [api/curl_examples.md](api/curl_examples.md) — curl examples for every endpoint.
- [api/postman_collection.json](api/postman_collection.json) — importable Postman collection.
- [FINAL_AUDIT.md](FINAL_AUDIT.md) — deliverables, verification matrix, PR map, limitations, and reviewer checklist.

### Decision records

- [ADR-0001 — Neo4j runtime, configuration, and test isolation](decisions/ADR-0001-neo4j-runtime-and-test-isolation.md)
- [ADR-0002 — Graph schema and temporal semantics](decisions/ADR-0002-graph-schema-and-temporal-semantics.md)
- [ADR-0003 — Idempotent write and validation semantics](decisions/ADR-0003-write-idempotency-and-validation.md)
- [ADR-0004 — Query, API, and export contracts](decisions/ADR-0004-query-api-and-export-contracts.md)

## Known limitations and open issues

- **Year-only dates collapse to 1 January.** This is a verified limitation in Person A's pipeline. Date-range
  queries must document the resulting false negatives for ranges that start after 1 January.
- **Stale `LINKED_TO` links are not deleted by default.** A later run with a different corpus can leave old
  links behind. This is accepted for the MVP and tracked as a backlog item.
- **The writer's live idempotency test is skipped** until a reachable Neo4j `.env` exists. The mocked
  validation/plan tests run without Neo4j.
- **Index-usage evidence is pending.** The Stage 3 integration test checks that the date-range `EXPLAIN`
  plan contains `event_date`; it cannot run without Aura.
- **The case-insensitive entity fallback is a non-indexed scan.** It runs only when exact normalized
  matching returns nothing.
- **Live API verification is pending Aura.** API tests use an injected fake client; no endpoint has been
  exercised against a real database yet.
- `starlette.testclient` reports an `httpx` deprecation advisory under the current dependency set. It is a
  warning, not an API failure.
- **Global `PRECEDES` recomputation is a batch operation.** It is idempotent but will need care if the graph
  grows large or writes become highly concurrent.
- **Docker Compose is untested** on this machine because Docker is unavailable in the shell.
- **Aura integration results are pending** until the owner creates the instance and fills `.env`.
- **OpenCode config behaviour:** The V2 documentation confirms the `instructions` array, and the running
  session loaded `contributions/person-b-graphdb/AGENTS.md` as an instruction source after the config was
  created. The CLI version could not be queried from the shell.

## Future consolidation

After the project consolidates, these documents should be considered for shared project documentation:

- the Neo4j setup and health-check instructions, into a shared setup guide;
- the architecture/data-flow section, into the overall project architecture;
- the testing commands and integration-test policy, into a shared testing guide;
- the graph API contract, into a shared API/consumer guide.

They are contribution-local now to avoid editing shared documents before team review.
