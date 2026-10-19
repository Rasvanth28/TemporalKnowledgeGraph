# Final audit — Graph DB & Backend lane

- **Date:** 2026-10-19
- **Final branch:** `feature/graphdb-export-e2e`
- **Status:** Implementation complete through Stage 6; all live-Neo4j verification is pending a configured
  `.env`.

## Deliverables vs plan

| Requirement | Status | Where |
|---|---|---|
| Stand up Neo4j (Aura primary, Compose alternative) | Config + docs done; Aura instance not created here | ADR-0001, `docker-compose.yml`, `.env.example` |
| Four indexes exactly | Implemented + unit-tested | `graphdb/indexes.cql` |
| Uniqueness constraints | Implemented + unit-tested | `graphdb/constraints.cql` |
| Schema application + health check | Implemented + unit-tested | `graphdb/apply_schema.py`, `graphdb/health.py` |
| Idempotent `MERGE` writer | Implemented + unit-tested | `graphdb/writer.py` |
| `DESCRIBES`, `MENTIONS`, `ABOUT`, `INVOLVES`, `PRECEDES`, `LINKED_TO` | Implemented | `graphdb/writer.py` |
| Event chain by entity | Implemented + unit-tested | `graphdb/queries.py` |
| Event chain by date range | Implemented + unit-tested | `graphdb/queries.py` |
| Event chain by topic | Implemented + unit-tested | `graphdb/queries.py` |
| Stable RMI fallback functions | Implemented + unit-tested | `event_by_id`, `events_in_date_range` |
| FastAPI layer | Implemented + unit-tested | `graphdb/api.py`, `contributions/person-b-graphdb/api/` |
| Postman collection / curl examples | Implemented | `contributions/person-b-graphdb/api/` |
| Flat event-key export from graph | Implemented + unit-tested | `graphdb/export.py` |
| Integration test: pipeline → Neo4j → query round-trip | Prepared; skipped without Aura | `graphdb/tests/test_e2e_pipeline_neo4j.py` |
| How-to-run documentation | Implemented | `README.md`, `PROPOSED_ROOT_README_SECTION.md`, `api/` |

## Verification summary

Verified locally:

```text
pytest -q                 106 passed, 5 skipped, 1 dependency warning
pip check                 No broken requirements found.
compileall graphdb        exit 0
documentation links       78 checked, 0 missing
Postman/fixture JSON      valid
```

Not executed because no Aura `.env` exists:

- live schema application and `SHOW INDEXES` behavior;
- live writer idempotency and out-of-order `PRECEDES` reconstruction;
- live query round-trip and `EXPLAIN` index evidence;
- live API and Postman/curl requests;
- Docker Compose (Docker unavailable in the shell).

Those are recorded as `NOT EXECUTED` in [TESTING.md](TESTING.md), not as passes.

## PR map and merge order

| PR | Branch | Base while stacked | Scope |
|---|---|---|---|
| PR 1 | `feature/graphdb-foundation` | `main` | Stage 0 + Stage 1 |
| PR 2 | `feature/graphdb-writer` | `feature/graphdb-foundation` | Stage 2 |
| PR 3 | `feature/graphdb-queries` | `feature/graphdb-writer` | Stage 3 |
| PR 4 | `feature/graphdb-api` | `feature/graphdb-queries` | Stage 4 |
| PR 5 | `feature/graphdb-export-e2e` | `feature/graphdb-api` | Stage 5 + Stage 6 |

All five branches are pushed. Because `gh` is not installed, PR descriptions are checked into
`contributions/person-b-graphdb/pr/` and are ready to paste into GitHub. Merge in order and retarget each PR
to `main` after the previous branch merges.

## Repository hygiene

- No root `README.md`, `PROJECT_PLAN.md`, `Documentation/`, `common/schema.py`, `pipeline/`, or `scripts/`
  file was modified.
- Shared-file changes are limited to the approved `requirements.txt`, `.env.example`, and new
  `docker-compose.yml`.
- `.git/info/exclude` contains only the local `opencode.json` line.
- `.env` is absent and was never printed or committed.
- `__pycache__`, `.venv`, and generated data are not staged.

## Known limitations and backlog

1. Year-only dates become 1 January, so date-range queries can miss them.
2. Stale `LINKED_TO` edges are not deleted by default.
3. Global `PRECEDES` rebuild is O(n) and batch-oriented.
4. `topic_name` may be satisfied by a constraint-owned equivalent index on some Neo4j versions; live
   observation is pending.
5. Case-insensitive entity fallback is a non-indexed scan.
6. Docker Compose is untested.
7. `starlette.testclient` emits an `httpx` deprecation warning under the current dependency set.
8. Live Aura evidence for schema, writer, queries, API, and export is pending.

## Reviewer checklist

1. Read [README.md](README.md), [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md), and [ARCHITECTURE.md](ARCHITECTURE.md).
2. Read the four ADRs in [decisions/](decisions/README.md).
3. Inspect the CQL files for exact index statements and approved constraints.
4. Inspect `graphdb/writer.py` for validation-before-write and in-transaction marker cleanup.
5. Inspect `graphdb/queries.py` for parameterized Cypher, guards, and stable return shapes.
6. Inspect `graphdb/api.py` for thin routes and Pydantic models.
7. Inspect `graphdb/export.py` for the Person C column contract.
8. Review [TESTING.md](TESTING.md) and distinguish passed, skipped, and not executable.
9. Confirm the shared-file scope above before merging.

## Next after Aura is configured

1. Fill `.env` locally, never in chat or git.
2. Run `python -m graphdb.health` and `python -m graphdb.apply_schema`.
3. Record the live `SHOW INDEXES` output, especially `Topic.name` / `topic_name`.
4. Run `python -m pytest -m integration`.
5. Record `EXPLAIN`/`PROFILE` evidence for the date-range lookup.
6. Run the API and execute the Postman/curl examples.
7. Commit the observed evidence into `TESTING.md` via a review PR.
