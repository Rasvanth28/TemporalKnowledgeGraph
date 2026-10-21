# Review guide — Graph DB & Backend lane

This guide is for a reviewer who has not seen the lane before. It explains why the lane exists, where it
sits, what to inspect first, and how to interpret the tests.

## 1. Motivation

Person A's pipeline already extracts articles, entities, events, topics, and confidence-scored event
links. Without a graph layer, those results cannot be traversed as a connected history, and Person C's
RMI cannot compare its date-key lookup against Neo4j's indexed fallback.

This lane builds the guaranteed-working graph and backend path:

- Neo4j stores the graph.
- The writer persists pipeline output idempotently.
- Queries return event chains by entity, date range, and topic.
- FastAPI exposes a stable contract.
- The flat export feeds Person C.

## 2. Existing architecture

Reused, unchanged:

- `common/schema.py` — shared dataclasses.
- `pipeline/` — Person A's extraction/linking/export.
- `scripts/run_pipeline.py` — Person A's pipeline entry point.
- `data/sample_articles.json` — official sample.
- The design document's four-index schema and relationship model.

New in this lane:

- `graphdb/` — connection, schema application, writer, queries, API, export, tests.
- `contributions/person-b-graphdb/` — documentation and ADRs.
- A local untracked `opencode.json` for session instructions.

## 3. Recommended inspection order

1. [README.md](README.md) — current status and scope.
2. [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) — requirements and acceptance criteria.
3. [ARCHITECTURE.md](ARCHITECTURE.md) and [diagrams/architecture.md](diagrams/architecture.md) — data flow.
4. [decisions/README.md](decisions/README.md) and the four ADRs — accepted decisions and trade-offs.
5. [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) — what changed and why.
6. [TESTING.md](TESTING.md) — exact environment, commands, results, gaps.
7. [FINAL_AUDIT.md](FINAL_AUDIT.md) — deliverables, verification matrix, PR map, and limitations.
8. `graphdb/` — implementation, tests, and CQL.
9. [PROPOSED_ROOT_README_SECTION.md](PROPOSED_ROOT_README_SECTION.md) — eventual shared setup text.

## 4. Representative article trace (planned)

This is an illustrative, **not executed** trace of the intended contract. It uses synthetic ids and must
not be presented as real pipeline output. The Stage 2 test fixture will provide a real, test-only version.

### JSON input (shape)

```json
{
  "results": [
    {
      "article": {
        "id": "art_review_001",
        "title": "Central bank raises rates",
        "date": "2026-03-05",
        "source": "example",
        "url": "https://example.invalid/review"
      },
      "entities": [
        {"id": "ent_review_bank", "name": "Example Bank", "type": "ORG"}
      ],
      "events": [
        {
          "event": {
            "id": "evt_review_001",
            "description": "Example Bank raised interest rates",
            "date": "2026-03-01",
            "type": "policy_change",
            "date_source": "explicit"
          },
          "entities": [
            {"id": "ent_review_bank", "name": "Example Bank", "type": "ORG"}
          ],
          "topic": {"name": "interest rates"},
          "source_text": "Example Bank raised interest rates on 1 March 2026."
        }
      ]
    }
  ],
  "links": []
}
```

### Cypher shape (parameterized, planned)

```cypher
MERGE (a:Article {id: $article.id})
  ON CREATE SET a.title = $article.title,
                a.date = date($article.date),
                a.source = $article.source,
                a.url = $article.url
MERGE (e:Event {id: $event.id})
  ON CREATE SET e.description = $event.description,
                e.date = date($event.date),
                e.type = $event.type,
                e.date_source = $event.date_source
MERGE (a)-[:DESCRIBES]->(e)
MERGE (n:Entity {id: $entity.id})
  ON CREATE SET n.name = $entity.name, n.type = $entity.type
MERGE (a)-[:MENTIONS]->(n)
MERGE (e)-[:INVOLVES]->(n)
MERGE (t:Topic {name: $topic.name})
MERGE (e)-[:ABOUT]->(t)
MERGE (a)-[:ABOUT]->(t)
```

The real writer will batch with `UNWIND`, validate endpoints, and rebuild `PRECEDES` after the batch.

### Query response (planned)

```json
{
  "event_id": "evt_review_001",
  "description": "Example Bank raised interest rates",
  "date": "2026-03-01",
  "date_source": "explicit",
  "type": "policy_change",
  "article_id": "art_review_001",
  "entities": [{"id": "ent_review_bank", "name": "Example Bank", "type": "ORG"}],
  "topic": "interest rates",
  "links": []
}
```

The actual response model is a Stage 4 Phase B decision.

## 5. Key functions to inspect later

| Function/module | What to check |
|---|---|
| `graphdb.config.load_neo4j_config` | Required env vars, no secrets in errors/repr |
| `graphdb.connection.Neo4jClient` | Small mockable interface; driver closed correctly |
| `graphdb.apply_schema` | Idempotent, rerunnable, equivalent-index handling, `SHOW INDEXES` verification |
| `graphdb.writer.write_pipeline_output` | Parameterized Cypher, transactions, idempotency counts, endpoint validation |
| `graphdb.writer.rebuild_precedes` | Global `(date, id)` chain, stale-edge deletion, transaction scope |
| `graphdb.queries.*` | Typed signatures, plain dicts/dataclasses, depth/limit guards, index use |
| `graphdb.api.*` | Thin routes, Pydantic models, error codes, no business logic |
| `graphdb.export.*` | Stable columns and `date_key` contract |

## 6. Decisions and rationale

- **Aura primary, Compose alternative.** Aura matches the project plan and avoids local setup; Compose is
  reproducible but untested because Docker is unavailable. See ADR-0001.
- **Both `Event-ABOUT` and derived `Article-ABOUT`.** Preserves the design doc and enables precise topic
  queries. See ADR-0002.
- **Global `PRECEDES`.** The design doc defines pure chronology independent of `LINKED_TO`; the chain is
  rebuilt after each batch. See ADR-0002 and ADR-0003.
- **Latest `LINKED_TO` wins.** Re-runs reflect the current corpus; stale-link cleanup is a known limitation.
  See ADR-0003.
- **Exact case-sensitive entity matching.** Keeps the `entity_name` index usable; a non-indexed fallback
  may run only when exact matching returns nothing. See ADR-0004.
- **FastAPI contract.** Chosen over Postman-only because Person C and a future frontend need a stable
  programmatic interface. See ADR-0004.

## 7. How to run and interpret tests

```powershell
python -m pytest
python -m pytest graphdb/tests -m "not integration"
python -m pytest graphdb/tests -m integration
```

Interpretation:

- Unit tests must pass without Neo4j.
- Integration tests skip when `NEO4J_URI` is unset; a skip is not a pass.
- `graphdb.health` failure usually means missing/wrong env vars, network/TLS, or an unavailable instance.
- `graphdb.apply_schema` should succeed twice in a row. A second-run failure is a rerunnability bug.
- `SHOW INDEXES` output must be recorded for the actual Neo4j version, especially for `Topic.name`.

## 8. Limitations and risks

- Year-only dates collapse to 1 January; date-range queries can miss them.
- Stale `LINKED_TO` links remain after a different-corpus run.
- Global `PRECEDES` recomputation will not scale indefinitely without redesign.
- Docker Compose is unverified here.
- Aura integration evidence is pending until credentials exist locally.
- The API contract is not yet specified; do not build a consumer against placeholders.
