# Person C — Research/RMI contribution

- **Owner:** Person C (Research/RMI lane)
- **Contribution id:** `person-c-rmi`
- **Branch:** `feature/rmi-core`
- **Current stage:** C2 — benchmark harness implemented and tested; synthetic results recorded. C3 is next.
  C4 (live Neo4j integration) is blocked until Person B's PRs #8–#12 merge and an Aura `.env` exists.

> This folder is the isolated documentation home for the Research/RMI lane. Code lives in `rmi/`.
> No Person A or Person B file is edited without explicit approval.

## Purpose

The lane investigates whether a learned index can answer date-key lookups faster than Neo4j's B+ tree
index, while falling back to Neo4j whenever the learned prediction is out of range or unconfident.

## Scope

1. A config-driven two-stage Recursive Model Index.
2. Max-training-error-bounded local search that guarantees correctness on training keys.
3. A benchmark harness comparing RMI lookup with an injectable fallback lookup.
4. An update-drift experiment with an idempotent `retrain_rmi()` trigger.
5. Live wiring to Person B's `graphdb/queries.py` fallback, after Person B merges.

## Implemented functionality and status

| Area | Status | Notes |
|---|---|---|
| `rmi/config.py` | **C1 complete** | Stage models and bucket count from `RMI_*` env vars |
| `rmi/keys.py` | **C1 complete** | Deterministic synthetic sorted uniform/clustered keys |
| `rmi/model.py` | **C1 complete** | Two-stage RMI with stage-1 bucket routing and per-bucket error windows |
| `rmi/train.py` | **C1 complete** | `train_rmi`, idempotent `retrain_rmi`, CLI summary |
| `rmi/fallback.py` | **C2 complete** | Injectable fallback contract; binary-search stand-in |
| `rmi/benchmark.py` | **C2 complete** | Same-query-set RMI vs fallback latency and correctness harness |
| Live Neo4j benchmark | **C4 blocked** | Needs Person B merged and Aura |
| Update-drift experiment | **C3 planned** | Insert new keys outside training range, retrain, compare |
| Neo4j integration | **C4 blocked** | Needs Person B PRs #8–#12 merged and Aura `.env` |
| `RESULTS.md` | **Draft scaffold** | Filled by C2/C3 and finalized in C4 |

## How to run

Inside `.venv`:

```powershell
python -m pytest rmi/tests -q
python -m rmi.train --keys 10000 --distribution uniform --seed 42
python -m rmi.benchmark --keys 10000 --queries 2000 --distribution uniform --seed 42 --repeats 3
```

Configuration is environment-only:

```dotenv
RMI_STAGE_MODELS=linear,linear
RMI_BUCKET_COUNT=128
```

These are not added to the shared `.env.example` while Person B's PRs are open. The consolidation PR will
propose them.

## Documentation map

- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md)
- [TESTING.md](TESTING.md)
- [REVIEW_GUIDE.md](REVIEW_GUIDE.md)
- [RESULTS.md](RESULTS.md)
- [AGENTS.md](AGENTS.md)
- [SESSION_HANDOFF.md](SESSION_HANDOFF.md)
- [decisions/README.md](decisions/README.md)
- [diagrams/architecture.md](diagrams/architecture.md)
- [PROPOSED_ROOT_README_SECTION.md](PROPOSED_ROOT_README_SECTION.md)

## PR map and dependencies

| PR | Branch | Scope | Depends on |
|---|---|---|---|
| C1 | `feature/rmi-core` | RMI core, config, synthetic keys, tests | `main` only |
| C2 | `feature/rmi-benchmark` | Benchmark harness with injectable fallback, tests | C1 merged (or stacked on C1) |
| C3 | `feature/rmi-drift` | `retrain_rmi()` experiment, drift metrics, RESULTS draft | C2 merged (or stacked on C2) |
| C4 | `feature/rmi-neo4j-integration` | Wire `graphdb.queries` fallback, live RMI vs B+tree benchmark, final RESULTS | **Person B PRs #8–#12 merged + Aura `.env`** |

C1–C3 have no Person B dependency. Only C4 does.

## Known limitations

- The current model supports exactly two stages. Stage count is read from config, and other counts fail
  with a clear error; additional stages are a backlog extension.
- Live Neo4j comparison numbers are pending C4.
- The independent benchmark fallback is an injected callable; the real B+ tree measurement requires Aura.
- Synthetic key distributions are not a substitute for the real exported event-key distribution.
