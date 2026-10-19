# PR 0001 — Graph DB foundation: contribution scaffold, Neo4j config, schema tooling

- **Base branch:** `main`
- **Head branch:** `feature/graphdb-foundation`
- **PR scope:** Stage 0 + Stage 1
- **Suggested title:** `feat: add Neo4j schema foundation and contribution docs`

## Summary

This PR starts the Graph DB & Backend lane. It creates the contribution documentation and decision records,
then implements the Neo4j foundation:

- environment-only Neo4j configuration;
- a small, mockable driver/session wrapper;
- a connection and server-metadata health check;
- the four design-document indexes, exactly;
- four approved uniqueness constraints;
- a rerunnable schema application and verification CLI;
- a documented Docker Compose alternative;
- unit tests, and a `test_`-namespaced integration test that auto-skips without Aura.

## What changed

- `contributions/person-b-graphdb/` — README, overview, architecture, ADRs, testing, review guide,
  handoff, proposed root README section, and diagram.
- `graphdb/` — config, connection, health, schema application, CQL files, and tests.
- `docker-compose.yml` — local Neo4j alternative, clearly marked untested here.
- `requirements.txt` — only the new pins actually installed and tested.
- `.env.example` — Neo4j placeholders only.

## Verification

```text
pytest -q                 61 passed, 1 skipped
pip check                 No broken requirements found.
compileall graphdb        exit 0
staged diff check         exit 0
documentation links       47 checked, 0 missing
```

The skipped test is the real-Neo4j integration test because `.env` / `NEO4J_URI` is not configured. It is
a skip, not a pass.

`graphdb.health` and `graphdb.apply_schema --verify-only` were run without `.env` and failed cleanly with a
missing-variable configuration error, exit code 1, and no secret values printed.

## Known limitations

- Live Aura schema behavior is not yet observed, including the `Topic.name` / `topic_name` interaction.
- Docker Compose is present but was not executed; Docker is unavailable in the development shell.
- The real-Neo4j integration test is skipped until the owner creates the instance and fills the local
  `.env`.

## Review focus

1. `contributions/person-b-graphdb/decisions/` — four Accepted ADRs.
2. `graphdb/indexes.cql` and `graphdb/constraints.cql` — exact statements.
3. `graphdb/apply_schema.py` — constraints first, equivalent-index handling, verification.
4. `graphdb/config.py` and `graphdb/connection.py` — no secrets in errors or repr.
5. `graphdb/tests/` — mocked unit tests and integration isolation.

## PR timing

This is **PR 1 of 5** in the Graph DB & Backend lane:

1. `feature/graphdb-foundation` — Stage 0 + Stage 1 (this PR)
2. `feature/graphdb-writer` — Stage 2
3. `feature/graphdb-queries` — Stage 3
4. `feature/graphdb-api` — Stage 4
5. `feature/graphdb-export-e2e` — Stage 5 + Stage 6
