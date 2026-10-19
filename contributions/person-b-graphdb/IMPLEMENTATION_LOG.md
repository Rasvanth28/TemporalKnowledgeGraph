# Implementation log

Chronological record of this lane. Entries are appended; historical entries are not rewritten except to
correct a factual error. No commit hashes or timestamps are invented.

## 2026-10-19 — Stage 0: contribution scaffold and local workflow

**Objective:** Create the isolated documentation set, accepted decision records, persistent OpenCode
instructions, and local untracked configuration required before any graph implementation.

**Branch:** `feature/graphdb-foundation`, created from `main` at `b0d9f08` after confirming local `main`
matched `origin/main`. No commit or push was performed.

**Files created:**

- `contributions/person-b-graphdb/README.md`
- `contributions/person-b-graphdb/PROJECT_OVERVIEW.md`
- `contributions/person-b-graphdb/ARCHITECTURE.md`
- `contributions/person-b-graphdb/IMPLEMENTATION_LOG.md`
- `contributions/person-b-graphdb/TESTING.md`
- `contributions/person-b-graphdb/REVIEW_GUIDE.md`
- `contributions/person-b-graphdb/AGENTS.md`
- `contributions/person-b-graphdb/SESSION_HANDOFF.md`
- `contributions/person-b-graphdb/PROPOSED_ROOT_README_SECTION.md`
- `contributions/person-b-graphdb/decisions/README.md`
- `contributions/person-b-graphdb/decisions/ADR-0001-neo4j-runtime-and-test-isolation.md`
- `contributions/person-b-graphdb/decisions/ADR-0002-graph-schema-and-temporal-semantics.md`
- `contributions/person-b-graphdb/decisions/ADR-0003-write-idempotency-and-validation.md`
- `contributions/person-b-graphdb/decisions/ADR-0004-query-api-and-export-contracts.md`
- `contributions/person-b-graphdb/diagrams/architecture.md`
- `opencode.json` (local, untracked)
- `.git/info/exclude` (local-only line appended)

**Reasoning:** The contribution folder is the only approved place for lane documentation. The local
OpenCode config points to the lane's `AGENTS.md` without creating a shared root `AGENTS.md` or modifying
the shared `.gitignore`. ADRs are grouped by concern rather than one per question so the decision history
stays readable.

**Alternatives considered:**

- A single root `AGENTS.md`: rejected because it changes shared project guidance.
- Editing the root `README.md` directly: rejected by the documentation isolation rule.
- One ADR per answer: rejected as too fragmented; four topic-level ADRs preserve rationale and links.
- Committing `opencode.json`: rejected; it is a local workflow preference, not shared project config.

**Tests or checks run:**

- `git status --short --branch` before branch creation: clean, `main` equal to `origin/main`.
- `git rev-list --left-right --count main...origin/main`: `0 0`.
- `git switch -c feature/graphdb-foundation main`: succeeded.
- Required-file check: 15 required files, 0 missing.
- Relative Markdown link check: 42 links checked, 0 missing.
- ADR metadata check: 4 ADRs, 0 metadata issues (all Accepted, dated 2026-10-19).
- `python -m json.tool opencode.json`: valid JSON; the instructions target exists.
- The running session reported `Instructions from: contributions/person-b-graphdb/AGENTS.md` after the
  config was created, confirming the local instruction wiring was picked up.
- `git check-ignore -v opencode.json`: matched `.git/info/exclude:9:opencode.json`.
- `git diff --name-only` and `git diff --cached --name-only`: empty.
- `git status --short --branch`: only `?? contributions/`.

**Results and failures:** All Stage 0 structural checks passed. No runtime tests were run because Stage 0
contains no executable code. No shared tracked file was modified, nothing was staged, and no commit or push
was performed.

**Links:**

- [ADR-0001](decisions/ADR-0001-neo4j-runtime-and-test-isolation.md)
- [ADR-0002](decisions/ADR-0002-graph-schema-and-temporal-semantics.md)
- [ADR-0003](decisions/ADR-0003-write-idempotency-and-validation.md)
- [ADR-0004](decisions/ADR-0004-query-api-and-export-contracts.md)
- [TESTING.md](TESTING.md)

**Next:** Review Stage 0, then implement Stage 1: Neo4j config/connection/health, CQL files, schema
application, Docker Compose alternative, dependency pins, unit tests, and integration tests if Aura is
reachable.

## 2026-10-19 — Stage 1: Neo4j foundation

**Objective:** Implement environment-only Neo4j configuration, a mockable driver/session wrapper, a
connection health check, the exact four design-document indexes, the four approved uniqueness constraints,
an idempotent schema application/verification CLI, the Docker Compose alternative, dependency pins, and
tests.

**Branch:** `feature/graphdb-foundation` (same branch as Stage 0). No commit or push was performed.

**Files created:**

- `graphdb/__init__.py`
- `graphdb/config.py`
- `graphdb/connection.py`
- `graphdb/health.py`
- `graphdb/apply_schema.py`
- `graphdb/indexes.cql`
- `graphdb/constraints.cql`
- `graphdb/tests/__init__.py`
- `graphdb/tests/conftest.py`
- `graphdb/tests/test_config.py`
- `graphdb/tests/test_connection.py`
- `graphdb/tests/test_schema_files.py`
- `graphdb/tests/test_apply_schema.py`
- `graphdb/tests/test_health.py`
- `graphdb/tests/test_neo4j_integration.py`
- `docker-compose.yml`

**Files modified (approved shared files):**

- `requirements.txt` — appended `fastapi==0.146.0`, `neo4j==6.4.1`, `opentelemetry-api==1.45.1`,
  `pytz==2026.5`, `starlette==1.9.0`, `uvicorn==0.54.0`.
- `.env.example` — appended Neo4j placeholders and URI examples.
- `.git/info/exclude` — only the local `opencode.json` line (Stage 0).

No `.gitignore` change, no root README/PROJECT_PLAN/Documentation/common/pipeline/scripts edit.

**Reasoning:** Constraints are applied before indexes because they are correctness-critical for `MERGE`
and their backing indexes can satisfy a required property by equivalence. The schema verifier checks
property coverage through `SHOW INDEXES` / `SHOW CONSTRAINTS` rather than assuming exact object names,
which handles the expected `Topic.name` / `topic_name` interaction without hiding it. Health errors redact
the configured password. Tests inject fake drivers/clients so unit behavior is runnable without Neo4j.

**Alternatives considered:**

- Applying indexes before constraints: rejected because a constraint can be blocked by an equivalent
  standalone index, leaving the uniqueness guarantee missing.
- Requiring exact index names during verification: rejected because a constraint-owned backing index is a
  valid equivalent and Neo4j may not allow both objects.
- Importing Person A's normalizer now: deferred; Stage 1 does not need it, and importing `pipeline.extract`
  would pull spaCy into the backend. ADR-0004 requires a small tested equivalent later.
- Using Docker for verification: not possible; Docker is unavailable in this shell.

**Checks run and results:**

- `python -m venv .venv` — created with Python 3.14.0 and pip 25.2. [VERIFIED]
- First `pip install -r requirements.txt` exceeded the 15-minute command timeout during installation and
  left the environment partial. No wheel failed. [VERIFIED]
- Retried `pip install -r requirements.txt` — succeeded; spaCy, pytest, python-dotenv, numpy, scikit-learn,
  and `en_core_web_sm` import cleanly. [VERIFIED]
- Installed the three approved direct additions — succeeded; new transitive pins observed exactly:
  `opentelemetry-api==1.45.1`, `pytz==2026.5`, `starlette==1.9.0`. No existing pins changed. [VERIFIED]
- `pip check` — `No broken requirements found.` [VERIFIED]
- `python -m compileall -q graphdb` — exit 0. [VERIFIED]
- `pytest graphdb/tests -m "not integration"` — `19 passed, 1 deselected`. [VERIFIED]
- `pytest pipeline/tests` — `42 passed`. [VERIFIED]
- `pytest -q` — `61 passed, 1 skipped` in 2.23s. The skipped test is the real-Neo4j integration test. [VERIFIED]
- `python -m graphdb.health` without `.env` — failed clearly with missing `NEO4J_URI`, `NEO4J_USER`,
  `NEO4J_PASSWORD`; exit 1. No secret values printed. [VERIFIED]
- `python -m graphdb.apply_schema --verify-only` without `.env` — the same clear configuration failure;
  exit 1. [VERIFIED]
- Final documentation link check — 47 links checked, 0 missing; ADR metadata unchanged (4 Accepted). [VERIFIED]
- Docker Compose — not executed because Docker is unavailable. YAML parsing was also not run because
  PyYAML is not installed and no new dependency was approved for it. [NOT EXECUTED]
- Aura — not reached because `.env` is missing. Integration test skipped. [NOT EXECUTED]

**Results and failures:** All Graph DB unit tests and all existing Person A tests pass. The live Neo4j
schema behavior, including the `Topic.name` / `topic_name` equivalent-index interaction, remains
unobserved until Aura credentials exist locally. The Compose path is unverified.

**Links:**

- [ADR-0001](decisions/ADR-0001-neo4j-runtime-and-test-isolation.md)
- [ADR-0002](decisions/ADR-0002-graph-schema-and-temporal-semantics.md)
- [ADR-0003](decisions/ADR-0003-write-idempotency-and-validation.md)
- [ADR-0004](decisions/ADR-0004-query-api-and-export-contracts.md)
- [TESTING.md](TESTING.md)

**Next:** Owner review of Stage 1. Then Stage 2: writer, fixture, idempotency tests, global `PRECEDES`
recompute, and endpoint validation.

## 2026-10-19 — Stage 2: idempotent writer

**Objective:** Implement the idempotent, parameterized Neo4j writer, a synthetic test fixture, endpoint
validation, global `PRECEDES` recomputation, idempotency/out-of-order tests, and documentation.

**Branch:** `feature/graphdb-writer`, stacked on `feature/graphdb-foundation` because PR 1 is not merged yet.

**Files created:**

- `graphdb/writer.py`
- `graphdb/tests/fixtures/pipeline_output.json`
- `graphdb/tests/test_writer_plan.py`
- `graphdb/tests/test_writer_validation.py`
- `graphdb/tests/test_writer_neo4j.py`
- `contributions/person-b-graphdb/pr/PR-0002-graphdb-writer.md`

**Files modified:**

- `contributions/person-b-graphdb/README.md`
- `contributions/person-b-graphdb/ARCHITECTURE.md`
- `contributions/person-b-graphdb/IMPLEMENTATION_LOG.md`
- `contributions/person-b-graphdb/TESTING.md`
- `contributions/person-b-graphdb/SESSION_HANDOFF.md`

**Reasoning:** The writer parses either `PipelineOutput` objects or the JSON shape into one `WritePlan`,
validates link endpoints against the batch and existing graph before any write, then uses `UNWIND` +
parameterized `MERGE` inside explicit transactions. Created-vs-matched counts use a temporary
`_person_b_batch` marker removed in the same transaction. `PRECEDES` is deleted and rebuilt globally in a
separate transaction in `(date, id)` order. Entities are deduplicated by id across articles; events and
articles must be unique. `Article-ABOUT` is derived from each article's event topics.

**Alternatives considered:**

- Counting creations with global before/after node counts: rejected because concurrent writes and
  relationships make it unreliable.
- Using APOC merge procedures: rejected because Aura free does not guarantee APOC availability.
- Restricting `PRECEDES` to `LINKED_TO` pairs: already rejected in ADR-0002.
- One transaction for the whole batch plus `PRECEDES`: rejected because the rebuild is a separate,
  independently verifiable phase.

**Checks run and results:**

- `python -m compileall -q graphdb` — exit 0. [VERIFIED]
- `pytest graphdb/tests -m "not integration" -q` — `33 passed, 2 deselected`. [VERIFIED]
- `pytest -q` — `75 passed, 2 skipped`. [VERIFIED]
- `pip check` — no broken requirements. [VERIFIED]
- `python -m graphdb.writer --input graphdb/tests/fixtures/pipeline_output.json` without `.env` — parsed the
  fixture and failed with a clear missing-variable configuration error; exit 1. [VERIFIED]
- Writer integration test — skipped because `NEO4J_URI` is unset. [NOT EXECUTED]
- Live idempotency and out-of-order `PRECEDES` test — not executed without Aura. [NOT EXECUTED]

**Results and failures:** All writer plan/validation unit tests pass, and the full suite has no
regressions. The live idempotency proof remains pending a reachable Neo4j instance.

**Links:**

- [ADR-0002](decisions/ADR-0002-graph-schema-and-temporal-semantics.md)
- [ADR-0003](decisions/ADR-0003-write-idempotency-and-validation.md)
- [TESTING.md](TESTING.md)
- [PR-0002](pr/PR-0002-graphdb-writer.md)

**Next:** Stage 3 queries, index-usage evidence, and the stable RMI fallback contract.

## 2026-10-19 — Stage 3: queries and fallback contract

**Objective:** Implement the stable query contract for Person C and the future API: event lookup,
date-range lookup, entity/date/topic chains, entity-name normalization, and index-evidence tooling.

**Branch:** `feature/graphdb-queries`, stacked on `feature/graphdb-writer` because PR 1 and PR 2 are not
merged yet.

**Files created:**

- `graphdb/queries.py`
- `graphdb/normalize.py`
- `graphdb/tests/test_normalize.py`
- `graphdb/tests/test_queries_unit.py`
- `graphdb/tests/test_queries_neo4j.py`
- `contributions/person-b-graphdb/pr/PR-0003-graphdb-queries.md`

**Files modified:**

- `contributions/person-b-graphdb/README.md`
- `contributions/person-b-graphdb/ARCHITECTURE.md`
- `contributions/person-b-graphdb/IMPLEMENTATION_LOG.md`
- `contributions/person-b-graphdb/TESTING.md`
- `contributions/person-b-graphdb/SESSION_HANDOFF.md`

**Reasoning:** Queries return plain dictionaries and use parameterized Cypher. Entity matching uses the
exact normalized name so the `entity_name` index remains usable; the case-insensitive fallback is isolated
and documented as a non-indexed scan. Chain traversal follows `LINKED_TO`, filters by `min_confidence`,
caps depth at a code constant, limits results, and orders chronologically. `date_key` mirrors
`pipeline/export.py`. `explain_events_in_date_range` exists specifically so the live integration test can
record index evidence.

**Alternatives considered:**

- Case-insensitive `toLower` as the primary entity match: rejected because it prevents use of the required
  index.
- Importing `pipeline.extract.normalize_name`: rejected because it pulls spaCy into the backend; the small
  copy is tested independently.
- Parameterizing variable-length depth directly: rejected because Cypher range bounds are not parameters;
  the code uses a constant cap plus a `length(path) <= $depth` filter.
- Returning driver node/relationship objects: rejected by the stable-contract rule.

**Checks run and results:**

- `python -m compileall -q graphdb` — exit 0. [VERIFIED]
- `pytest graphdb/tests -m "not integration" -q` — `48 passed, 3 deselected`. [VERIFIED]
- `pytest -q` — `90 passed, 3 skipped`. [VERIFIED]
- `pip check` — no broken requirements. [VERIFIED]
- Live query round-trip and `EXPLAIN` index evidence — skipped without `NEO4J_URI`. [NOT EXECUTED]

**Results and failures:** Unit coverage passes with no regressions. Query behavior against Neo4j and the
`event_date` index plan remain unobserved until Aura is configured.

**Links:**

- [ADR-0004](decisions/ADR-0004-query-api-and-export-contracts.md)
- [TESTING.md](TESTING.md)
- [PR-0003](pr/PR-0003-graphdb-queries.md)

**Next:** Stage 4 API proposal and implementation.
