# PR C4 — Live RMI vs Neo4j B+ tree integration

- **Status:** Implemented on `feature/rmi-neo4j-integration` (2026-10-21); results in root `RESULTS.md`.
- **Base branch:** updated `main`
- **Head branch:** `feature/rmi-neo4j-integration`
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

## Outcome

- Dependencies resolved: Person B's work is on `main` and the Aura `.env` exists.
- The fallback adapter is `rmi.live.neo4j_lower_bound`, injected into `DateIndex` (the plan said `rmi/fallback.py`; it sits
  next to the live code instead, so `rmi/fallback.py` stays free of Neo4j imports).
- The benchmark uses the id-only form of `graphdb.queries`' date-range query, so it measures the index, not the
  entity/topic fan-out.
