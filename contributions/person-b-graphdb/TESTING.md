# Testing — Graph DB & Backend lane

## 1. Environment

Observed on 2026-10-19; updated after the Stage 1 environment setup.

| Item | Value | Label |
|---|---|---|
| OS shell | Windows / PowerShell | [VERIFIED] |
| Python | 3.14.0 | [VERIFIED] |
| `pip` (global) | 26.0.1 | [VERIFIED] |
| `pip` (inside `.venv`) | 25.2 | [VERIFIED] |
| Repository branch at start | `main`, `b0d9f08`, equal to `origin/main` | [VERIFIED] |
| Working tree at start | Clean | [VERIFIED] |
| `.venv` | Present, Python 3.14.0 | [VERIFIED] |
| `.env` | Missing | [VERIFIED] |
| spaCy | Installed in `.venv` (`3.8.16`) | [VERIFIED] |
| pytest | Installed in `.venv` (`9.1.1`) | [VERIFIED] |
| Neo4j driver | Installed in `.venv` (`6.4.1`) | [VERIFIED] |
| FastAPI / Uvicorn | Installed in `.venv` (`0.146.0` / `0.54.0`) | [VERIFIED] |
| Docker CLI | Not available on `PATH` | [VERIFIED] |
| Aura instance | Not configured; `.env` absent | [OPEN] |

Stage 0 contains no executable code. Stage 1 contains the config/connection/health/schema modules.

## 2. Prerequisites for later stages

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

For integration tests, the owner must create a local `.env` from `.env.example` and fill:

```text
NEO4J_URI
NEO4J_USER
NEO4J_PASSWORD
NEO4J_DATABASE
```

Do not paste credentials into chat, logs, documentation, or commits. Integration tests use the same
single Aura database and therefore only operate on `test_`-prefixed ids.

## 3. Stage 0 checks

### Structural checks

```powershell
Get-ChildItem -Recurse contributions/person-b-graphdb
git status --short --branch
git diff --stat
```

Expected:

- Every file listed in [README.md](README.md) exists.
- All relative Markdown links resolve.
- No tracked shared file is modified.
- `opencode.json` is untracked and excluded locally.

### Result

| Check | Expected | Actual | Status |
|---|---|---|---|
| Contribution file set exists | All required files | 15 required files, 0 missing | **Passed** |
| Relative documentation links | All resolve | 42 links checked, 0 missing | **Passed** |
| Shared tracked files untouched | Only new contribution files | `git diff --name-only` and staged diff empty; `git status` shows only `?? contributions/` | **Passed** |
| Local `opencode.json` excluded | Appears as ignored/untracked, never staged | `git check-ignore -v opencode.json` reports `.git/info/exclude:9:opencode.json` | **Passed** |
| `opencode.json` syntax | Valid JSON, target exists | `python -m json.tool` succeeded; `AGENTS.md` exists | **Passed** |
| OpenCode instruction loading | `AGENTS.md` is loaded from the local config | The running session reported `Instructions from: contributions/person-b-graphdb/AGENTS.md` after config creation | **Passed** |
| ADR metadata | Four ADRs, Accepted, 2026-10-19 | 4 ADRs, 0 metadata issues | **Passed** |

This is the Stage 0 snapshot. Stage 1 later added `graphdb/`, `docker-compose.yml`, and the approved
`requirements.txt` / `.env.example` modifications; the worktree status in the Stage 1 results reflects the
new set.

## 4. Stage 1 tests and results

### Unit tests (mocked, always runnable)

| Test | Purpose |
|---|---|
| Config validation | Missing/blank `NEO4J_*` variables fail with clear errors and no secret values |
| Config repr | Password never appears in `repr()` or error text |
| Connection wrapper | Driver/session delegation is mockable |
| CQL files | Exactly four required indexes and four approved constraints |
| Schema application | Rerunnable; equivalent-index conflict is handled and verified |
| Schema verification | Required `SHOW INDEXES` coverage is enforced |
| Health report | Success/failure paths return correct status and database/version fields |

### Integration tests (real Neo4j)

Marked `@pytest.mark.integration`; auto-skipped when `NEO4J_URI` is unset.

| Test | Purpose |
|---|---|
| Health | `driver.verify_connectivity()` and server metadata query succeed |
| Schema apply twice | No errors, no duplicate schema objects |
| Schema inspection | Four indexes/constraint coverage, including the `Topic.name` interaction |
| Probe cleanup | Create one exact `test_` node, delete only that node in `finally` |

Never run a database wipe or a broad delete.

### Regression

```powershell
python -m pytest
```

This runs Person A's existing tests plus the new unit tests. Integration tests skip without `NEO4J_URI`.
No Person A files are modified.

### Observed Stage 1 command results

```text
python -m venv .venv
.\.venv\Scripts\python.exe --version
Python 3.14.0

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
[first attempt exceeded the 15-minute command timeout while installing; no wheel failed]
[retry succeeded]

.\.venv\Scripts\python.exe -m pip install neo4j==6.4.1 fastapi==0.146.0 uvicorn==0.54.0
Successfully installed fastapi-0.146.0 neo4j-6.4.1 opentelemetry-api-1.45.1
pytz-2026.5 starlette-1.9.0 uvicorn-0.54.0

.\.venv\Scripts\python.exe -m pip check
No broken requirements found.

.\.venv\Scripts\python.exe -m compileall -q graphdb
(exit 0)

.\.venv\Scripts\python.exe -m pytest graphdb/tests -m "not integration" -q
19 passed, 1 deselected

.\.venv\Scripts\python.exe -m pytest pipeline/tests -q
42 passed

.\.venv\Scripts\python.exe -m pytest -q
61 passed, 1 skipped
```

### Stage 2 writer results

```text
python -m compileall -q graphdb
(exit 0)

python -m pytest graphdb/tests -m "not integration" -q
33 passed, 2 deselected

python -m pytest -q
75 passed, 2 skipped

python -m pip check
No broken requirements found.

python -m graphdb.writer --input graphdb/tests/fixtures/pipeline_output.json
Writer configuration error: Missing required Neo4J environment variable(s)
[exit 1; fixture parsed successfully; no secret values printed]
```

The Stage 2 integration test `test_writer_neo4j.py` was skipped because `NEO4J_URI` is unset. It is the
live proof of idempotency and the global `PRECEDES` rebuild, including the out-of-order insertion case.

### Stage 3 query results

```text
python -m compileall -q graphdb
(exit 0)

python -m pytest graphdb/tests -m "not integration" -q
48 passed, 3 deselected

python -m pytest -q
90 passed, 3 skipped

python -m pip check
No broken requirements found.
```

Live query and index evidence are not executed without Aura. The prepared integration test
`graphdb/tests/test_queries_neo4j.py::test_query_round_trip_and_index_evidence` writes the fixture, checks
entity/date/topic query results, and asserts that the `EXPLAIN` plan for the date-range lookup contains
`event_date`. Its output is required in this file before Stage 3 can be called live-verified.

### Index-usage evidence

| Query | Evidence | Status |
|---|---|---|
| `MATCH (e:Event) WHERE e.date >= date($start) AND e.date <= date($end) RETURN e.id` | `EXPLAIN` plan must contain `event_date` | **Not executable without Aura** |
| `MATCH (n:Entity {name: $name})` | Exact name match uses `entity_name`; integration test exercises it | **Not executable without Aura** |
| `MATCH (n:Entity) WHERE toLower(n.name) = toLower($name)` | Deliberately non-indexed fallback; documented in code | **By design** |

### Stage 4 API results

```text
python -m compileall -q graphdb
(exit 0)

python -m pytest graphdb/tests/test_api.py -q
10 passed

python -m pytest graphdb/tests -m "not integration" -q
58 passed, 3 deselected

python -m pytest -q
100 passed, 3 skipped, 1 warning

python -m pip check
No broken requirements found.
```

API tests use an injected fake Neo4j client. Live HTTP requests against Aura are not executed without a
configured `.env`. The Postman collection JSON parses successfully; curl examples are documented but not
executed against a live server.

One warning is emitted: `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated;
install httpx2 instead.` It is a dependency advisory for the test client, not an API behavior failure.

### Stage 5 export results

```text
python -m graphdb.export --output data/exports/graph_event_keys.csv
[not executable without .env]

python -m pytest graphdb/tests/test_export_unit.py -q
6 passed

python -m pytest graphdb/tests -m "not integration" -q
64 passed, 5 deselected

python -m pytest -q
106 passed, 5 skipped, 1 warning
```

The unit test asserts `EVENT_KEY_COLUMNS == pipeline.export.EVENT_KEY_COLUMNS` and checks date-key
computation, sorting, CSV header/order, missing article ids, and row filtering. The live export test is
skipped without `NEO4J_URI`.

### Stage 6 end-to-end results

The prepared `test_e2e_pipeline_neo4j.py` runs:

```text
data/sample_articles.json
  -> Person A's run_pipeline(JsonFileSource, SpacyExtractor, LinkConfig)
  -> PipelineWriter
  -> event_by_id / events_in_date_range
  -> graph export
  -> comparison with pipeline.export.write_event_keys_csv
```

It is skipped without `NEO4J_URI`. It cleans up the exact article/event/entity/topic ids produced by that
run and never wipes the database. No live result is claimed.

Final documentation audit: 78 relative links checked, 0 missing; Postman and fixture JSON parse cleanly.

## 5. Results

### Passed

Stage 0 structural checks, command results observed on 2026-10-19:

```text
git status --short --branch
## feature/graphdb-foundation
?? contributions/

git diff --stat
(empty)

git diff --cached --stat
(empty)

git check-ignore -v opencode.json
.git/info/exclude:9:opencode.json	opencode.json

python -m json.tool opencode.json
opencode.json: valid JSON

required_files=15 missing=0
checked_links=42 missing_links=0
adrs=4 metadata_issues=0
```

These are structural/documentation checks, not runtime tests.

Stage 1 mocked-runtime checks also passed:

- `graphdb/tests -m "not integration"`: 19 passed, 1 deselected.
- Person A pipeline tests: 42 passed.
- Full suite: 61 passed, 1 skipped.
- `pip check`: no broken requirements.
- `compileall`: exit 0.

The health and schema CLIs were run without `.env` and failed cleanly with a missing-variable
configuration error and exit code 1; no secret values were printed. This is the intended failure path, not a
successful Neo4j connection.

Stage 2 writer checks:

- `graphdb/tests -m "not integration"`: 33 passed, 2 deselected.
- Full suite: 75 passed, 2 skipped.
- Writer CLI parsed the fixture and failed only at configuration, as expected without `.env`.
- Live writer idempotency/out-of-order test: skipped without Neo4j.

Stage 3 query checks:

- `graphdb/tests -m "not integration"`: 48 passed, 3 deselected.
- Full suite: 90 passed, 3 skipped.
- Live query round-trip and `EXPLAIN` index evidence: not executable without Neo4j.

Stage 4 API checks:

- `graphdb/tests/test_api.py`: 10 passed.
- `graphdb/tests -m "not integration"`: 58 passed, 3 deselected.
- Full suite: 100 passed, 3 skipped, 1 dependency warning.
- Live HTTP calls against Aura: not executable without `.env`.

Stage 5 export checks:

- `graphdb/tests/test_export_unit.py`: 6 passed.
- Column contract equals `pipeline.export.EVENT_KEY_COLUMNS`.
- Live graph export: skipped without `NEO4J_URI`.

Stage 6 end-to-end checks:

- `pytest -q`: 106 passed, 5 skipped, 1 dependency warning.
- Official sample pipeline → writer → query → export: skipped without `NEO4J_URI`.

### Failed

None observed in Stages 0–6.

### Skipped

- Aura integration (`test_health_schema_and_cleanup_round_trip`): skipped because `NEO4J_URI` is unset.
  Exact pytest reason: `NEO4J_URI is not set; integration test skipped`. This is not a pass. The live schema,
  `SHOW INDEXES`, and `Topic.name` interaction remain unobserved.
- Docker Compose: not executable because Docker is unavailable in the current shell.
- Writer integration (`test_writer_neo4j.py`): skipped because `NEO4J_URI` is unset. It exercises write →
  write again → out-of-order insertion and asserts the PRECEDES chain and counts.
- Query integration (`test_queries_neo4j.py`): skipped because `NEO4J_URI` is unset. It exercises the query
  round-trip and the date-range `EXPLAIN` index evidence.
- API live calls: not executed. The API unit tests use an injected fake client; no HTTP server was started
  against Aura because `.env` is missing.
- Export integration (`test_export_neo4j.py`): skipped without `NEO4J_URI`.
- End-to-end pipeline integration (`test_e2e_pipeline_neo4j.py`): skipped without `NEO4J_URI`.

### Not executable

- Live `python -m graphdb.health`: requires a local `.env` with Aura settings.
- Live `python -m graphdb.apply_schema`: same dependency; the mocked path is tested.
- Docker Compose YAML parse: PyYAML is not installed and no new dependency was approved for parsing only.
- Official pipeline sample round-trip: writer and queries exist (Stages 2–3), but a full end-to-end Aura
  round-trip is Stage 6 and requires a configured `.env`.
- Live `EXPLAIN`/`PROFILE` evidence: not executable without Aura; the integration test is prepared.
- Live API and Postman/curl requests: not executable without a configured server-side `.env`.
- Live graph export and official-sample end-to-end round-trip: not executable without Aura.

## 6. Evidence policy

- Results are recorded from commands actually run.
- If a command cannot run, it is listed under “could not execute” rather than guessed.
- `EXPLAIN`/`PROFILE` output for index usage is required in Stage 3 and will be pasted or summarized with
  the exact query and observed plan.
- Year-only dates are a known correctness limitation, not a test failure of the graph lane.
