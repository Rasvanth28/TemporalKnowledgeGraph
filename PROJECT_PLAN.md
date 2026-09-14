# Temporal Knowledge Graph — Team Plan

1-week MVP sprint (inside a ~2-week window), 3 people, designed so beginners learn real production-engineering practice while building toward everything in `Documentation/DBS_Temporal_Knowledge_Graph`.

## Context

This repo starts green-field: an empty `README.md` and one design document (`Documentation/DBS_Temporal_Knowledge_Graph`, a BCSE302P DB Systems lab report) describing the target system — no code exists yet.

The documented system has two layers:

1. **Neo4j** — the real, working graph database storing `Article`/`Event`/`Entity`/`Topic` nodes and relationships (`DESCRIBES`, `MENTIONS`, `ABOUT`, `INVOLVES`, `PRECEDES`, `LINKED_TO`), fed by an NLP pipeline that does NER + event extraction + confidence-scored event linking. This is the guaranteed-working baseline.
2. **RMI (Recursive Model Index)** — an experimental learned-index research layer benchmarked against Neo4j's default B+ tree indexing, explicitly allowed to "fail" as a research finding without sinking the project. It must fall back to Neo4j whenever unconfident, and must handle the "update-drift" problem (new events arrive continuously; the model is only retrained periodically).

The point of this build is less about the DB-systems research result and more about using this project to teach two coding-beginner teammates how real production engineering teams operate — git workflow, code review, issue tracking, contracts between modules, testing, docs — under an aggressive 1-week fast-track.

**Everything in the document must eventually be covered — nothing is dropped.** Week 1 ships a real, working, demoable end-to-end MVP; anything not fully built in Week 1 is deliberately simplified rather than omitted, and the codebase is architected (interfaces, config-driven behavior, no hardcoded shortcuts that block growth) so every simplified piece can be extended toward the document's full ambition afterward without a rewrite. Each such item is tracked as a visible backlog issue on the GitHub Project board, not silently forgotten.

## Roles

- **Person A — ML/NLP Pipeline lane**: entity/event extraction, link scoring.
- **Person B — Graph DB & Backend lane**: Neo4j schema, writer, query API, thin frontend.
- **Person C — Research/RMI lane**: learned index, error bounds, retrain/drift benchmark.

Front end is intentionally folded into Person B's lane as a thin last-mile layer, matching the doc's own guidance (§2.1: build it last, raw Cypher/Postman is an acceptable substitute if time is short).

## Process scaffolding (the "how top MNCs organize work" part — set up Day 0, applies to all three)

1. **Repo hygiene**: proper Python `.gitignore` (`__pycache__/`, `.env`, `venv/`, `.DS_Store` already covered), `requirements.txt`, `.env.example` for secrets (Neo4j URI/user/password), non-empty `README.md` with setup instructions.
2. **GitHub Issues + Projects**: one Kanban board (Backlog / In Progress / In Review / Done). Every subtask below becomes an issue, assigned to its owner.
3. **Branching model**: `main` is protected; work happens on `feature/<lane>-<short-desc>` branches; every change lands via a Pull Request with at least one teammate's review/approval before merge — this is the core habit to teach, so no direct pushes to `main` after Day 0.
4. **Shared contract first**: before any lane writes real logic, all three agree on one shared schema module (`common/schema.py` or `SCHEMA.md`) defining the exact shape of `Article`/`Event`/`Entity`/`Topic` objects and relationships, matching Documentation §2.3.2's tables. This is the seam between Person A's output and Person B's Neo4j writer, and decouples Person C (who can train against an exported flat file instead of a live DB connection) so no lane blocks on another.
5. **Daily 15-min standup**: what I did / doing / blockers — even async in a chat thread, teaches the ritual.
6. **Definition of done** per subtask: code merged via reviewed PR + has at least one test + README section updated.

## Proposed repo structure

```
TemporalKnowledgeGraph/
├── README.md
├── requirements.txt
├── .env.example
├── docker-compose.yml        # Neo4j (alternative: Neo4j Aura free tier, zero local setup)
├── Documentation/
├── common/
│   └── schema.py             # shared Article/Event/Entity/Topic + relationship dataclasses (Day 0, joint)
├── data/
│   └── sample_articles.json  # ~20-30 hand-picked articles across 3-4 event chains
├── pipeline/                 # Person A
│   ├── extract.py            # NER + event extraction
│   ├── link.py               # confidence-scored linking
│   └── tests/
├── graphdb/                  # Person B
│   ├── indexes.cql           # per doc §2.3.2's CREATE INDEX statements
│   ├── writer.py             # MERGE-based idempotent writes
│   ├── queries.py            # chain-by-entity/date/topic queries
│   ├── api.py                # thin FastAPI layer (or Postman collection if time-short)
│   └── tests/
├── rmi/                       # Person C
│   ├── model.py               # 2-stage RMI (stage-1 bucket router, stage-2 linear predictors)
│   ├── train.py
│   ├── benchmark.py           # RMI vs Neo4j B+ tree latency
│   └── tests/
└── scripts/
    └── run_pipeline.py       # orchestrates ingest → extract → link → write
```

## Day-by-day (1 week)

- **Day 0/1 (all three, ~2-3h together)**: repo hygiene, GitHub Project + issues created, branch/PR convention agreed, `common/schema.py` written jointly, dataset picked (`data/sample_articles.json`), Neo4j instance stood up (Aura free tier recommended to avoid local setup pain), `.env` shared. Everyone does one "practice PR" (e.g., add their name to README) to learn the branch→PR→review→merge loop before real work starts.
- **Day 2-3**: parallel lane work (see subtasks below), daily standup.
- **Day 4**: integration — Person A's pipeline output flows into Person B's Neo4j writer on the sample dataset end-to-end; Person B exports a flat event-key dataset for Person C; Person C trains RMI v1 and runs first benchmark.
- **Day 5**: testing/hardening — unit + integration tests, PR review pass, bug fixes; Person C runs the update-drift experiment (insert a batch of "new" events not in training, measure RMI accuracy/latency before vs after a simulated retrain).
- **Day 6**: docs + polish — README finished, `RESULTS.md` summarizing RMI-vs-B+tree findings (a losing result is still a valid, reportable finding per the doc's own framing), short demo recorded, quick retro (what worked / what to change).
- **Day 7**: buffer / demo day.
- **Week 2+ (not day-by-day planned here)**: work directly off the `Backlog — Future Scope` column populated during Week 1 — custom-trained extraction model, real scheduler for retraining, additional RMI stages, real frontend, live data feed. Nothing new to design; Week 1's interfaces are what make this pure addition rather than rework.

## Per-person subtasks

**Person A — ML/NLP Pipeline**
1. Scaffold `pipeline/` + tests; add spaCy (off-the-shelf model — no custom training in 1 week) to `requirements.txt`.
2. NER: extract PERSON/ORG/LOCATION/POLICY-type entities from article text, behind an `Extractor` interface so a fine-tuned/custom model can be swapped in later without touching callers.
3. Event extraction: pragmatic, explainable approach — main clause + date (regex/`dateutil`), not SOTA — same swappable-interface treatment.
4. Linking/confidence scoring: combine shared-entity overlap, topic similarity (TF-IDF or simple embedding cosine), and date proximity into one confidence score + reason string, per doc §2.3.1/§2.3.2.
5. Conform output to `common/schema.py` (the Day-0 contract with Person B).
6. Unit tests on the sample dataset.
7. Short design-notes README section (what trade-offs were made and why).
8. Near end of week: export/hand off event records with numeric date keys for Person C's RMI training.

**Person B — Graph DB & Backend**
1. Stand up Neo4j (Aura or `docker-compose.yml`); share `.env.example`.
2. Implement schema + the four indexes from doc §2.3.2 exactly (`event_date`, `event_type`, `entity_name`, `topic_name`).
3. `writer.py`: idempotent `MERGE`-based writer consuming `common/schema.py` objects → nodes + `DESCRIBES`/`MENTIONS`/`ABOUT`/`INVOLVES`/`PRECEDES`/`LINKED_TO`.
4. `queries.py`: event-chain-by-entity, by-date-range, by-topic.
5. Thin, documented API (`FastAPI` recommended) exposing those queries as a stable contract; a bare Postman collection is an acceptable fallback if time runs short (doc §2.1 explicitly allows this) — either way, a real frontend can be built later against the same API without backend changes.
6. Export flat event-key dataset for Person C once the graph is populated.
7. Integration test: sample data → pipeline → Neo4j → query round-trip.
8. README section: how to run Neo4j + API locally.

**Person C — Research/RMI**
1. Scaffold `rmi/`; add `numpy`/`scikit-learn`.
2. Implement a simple 2-stage RMI (Kraska et al.): stage-1 model buckets keys, stage-2 small linear/regression models predict exact position — read stage count and per-stage model type from config rather than hardcoding, so more stages/richer models can be added later purely via config. Can start against synthetic sorted keys so this lane isn't blocked waiting on Neo4j, then switch to Person B's real export.
3. Compute each stage-2 model's max training error → size the bounded local-search correction window (this is what guarantees correctness).
4. Fallback path to Neo4j lookup on low-confidence/out-of-range predictions (wired to Person B's `queries.py` at integration time).
5. `benchmark.py`: measure/log lookup latency, RMI vs Neo4j B+ tree, same query set.
6. Update-drift experiment: implement retraining as a standalone `retrain_rmi()` function/script (idempotent, manually triggered for now, but ready to be wired to a real scheduler later per the doc's "weekly retrain"), then insert a batch of new events outside the training range and measure accuracy/latency before vs after one manually-triggered retrain — this directly answers the doc's stated "central open question."
7. `RESULTS.md` with findings.
8. Unit tests for training and error-bound correctness.

## Week-1 MVP scope vs. full document scope (nothing dropped, just sequenced)

Every row ships a working Week-1 version; the "designed to extend to" column is why the corresponding subtasks insist on clean interfaces instead of shortcuts. Each "later" item gets its own backlog issue on the GitHub Project board (column: `Backlog — Future Scope`), so the roadmap stays visible rather than implicit.

| Doc feature | Week-1 MVP version | Built so it can extend to (backlog) |
|---|---|---|
| NER/event extraction | Off-the-shelf spaCy model + rule-based date extraction, behind an `Extractor` interface | Fine-tuned/custom NER model swapped in behind the same interface, no caller changes |
| Retrain scheduling | `retrain_rmi()` is a standalone, idempotent, manually-triggered function/script | Same function wired to a real scheduler (cron/Airflow/GitHub Action on a timer) for the doc's "weekly retrain" — no logic change, only a trigger |
| RMI model | Simple 2-stage linear-regression RMI, stage count/model type read from config, not hardcoded | Additional stages / non-linear per-stage models added via config, per Kraska et al.'s fuller design |
| Frontend | Documented REST API + Postman collection (matches doc §2.1's own "prove it with Cypher/Postman first" guidance) | A real UI built directly on the same stable API, no backend changes needed |
| Dataset | Small hand-curated set (~20-30 articles, 3-4 visible event chains) loaded via one `data/` ingestion function | Same ingestion function pointed at a live news feed later — only the source changes, not the pipeline |
| Topic similarity | TF-IDF/keyword cosine similarity | Swappable for sentence-embedding similarity behind the same scoring function signature |

**Extensibility ground rules for all three lanes** (this is what "capable of handling future changes" means in practice, and is itself a lesson in production engineering):
- No lane hardcodes today's shortcut in a way that requires rewriting callers later — new behavior should be addable by swapping an implementation behind an existing interface/config flag, not by restructuring.
- Config (dataset path, Neo4j credentials, model choice, stage count) lives in `.env`/config files, never hardcoded in logic.
- Every module the other two lanes depend on (`common/schema.py`, `graphdb/queries.py`, the RMI lookup entrypoint) is treated as a stable contract — changing its shape requires a PR the other owner reviews, exactly like a real cross-team API change would.

## Verification / demo (end of week)

Run `scripts/run_pipeline.py` over `data/sample_articles.json` end-to-end: pipeline extracts + links → Neo4j is populated and indexed → a query (via API or Cypher) returns a real, correct chain of linked events → `benchmark.py` prints RMI-vs-B+tree latency numbers plus the drift-experiment result → `README.md`/`RESULTS.md` are current → GitHub Project board shows all planned issues in "Done," each merged through a reviewed PR.
