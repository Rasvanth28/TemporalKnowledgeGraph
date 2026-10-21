# PR C4 — Live RMI vs Neo4j B+ tree integration (BLOCKED)

- **Status:** **Draft — do not open until dependencies merge.**
- **Base branch:** updated `main`
- **Head branch:** `feature/rmi-neo4j-integration` (not created yet)
- **PR scope:** C4
- **Suggested title:** `feat: benchmark RMI against Neo4j fallback`

## Hard dependencies

This PR **requires Person B's PRs #8–#12 to be merged first**:

| Dependency | Why |
|---|---|
| Person B PR #8–#12 merged | Provides `graphdb/queries.py` on `main` |
| `graphdb.queries.events_in_date_range` | Real fallback lookup contract |
| `graphdb.queries.event_by_id` | Real fallback lookup contract |
| Aura `.env` configured by the owner | Enables live Neo4j measurements |
| Real exported event-key dataset | Real key distribution instead of synthetic stand-ins |

Do not branch from a Person B `feature/graphdb-*` branch. Branch from updated `main` after the merges.

## Planned work

1. Add a thin `rmi/fallback.py` adapter around Person B's stable query functions.
2. Inject that adapter into the existing `benchmark_lookup` harness without changing measurement logic.
3. Run the live RMI-vs-B+tree benchmark on the exported real `date_key` dataset.
4. Run the drift experiment against real/new keys.
5. Finalize `contributions/person-c-rmi/RESULTS.md` and propose root `RESULTS.md`.
6. Record exact commands and observed results in `TESTING.md`.

## Current blockers

- Person B PRs #8–#12 are open but not merged.
- No Aura `.env` exists on the development machine.
- No real exported event-key CSV is available yet.

Until those are resolved, this PR cannot be opened or implemented honestly.
