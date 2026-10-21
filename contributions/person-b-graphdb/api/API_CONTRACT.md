# Graph API contract

- **Status:** Implemented in Stage 4. Reviewable in PR 4; changes are stable-contract changes and need
  review from the consuming lane.
- **Base URL (local):** `http://127.0.0.1:8000`
- **OpenAPI:** `/openapi.json` and `/docs`
- **Configuration:** `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`

The API is a thin layer over `graphdb/queries.py`. Route handlers validate input, call the query
functions, and serialize plain dictionaries. No graph logic lives in routes.

## Endpoints

| Method | Path | Query/params | Returns | Notes |
|---|---|---|---|---|
| `GET` | `/health` | none | `Health` | `200` when Neo4j is reachable; `503` when degraded |
| `GET` | `/events/{event_id}` | path: event id | `Event` | `404` when missing |
| `GET` | `/events` | `start`, `end`, `limit`, `offset` | `Event[]` | inclusive native `Event.date` range |
| `GET` | `/chains/entity` | `name`, `min_confidence`, `depth`, `limit` | `Chain` | exact normalized entity name, optional non-indexed fallback |
| `GET` | `/chains/topic` | `topic`, `min_confidence`, `depth`, `limit` | `Chain` | exact topic name |
| `GET` | `/chains/date-range` | `start`, `end`, `min_confidence`, `depth`, `limit` | `Chain` | range-seeded chains |

## Validation limits

| Parameter | Rule |
|---|---|
| `limit` | `1..1000` |
| `offset` | `>= 0` |
| `min_confidence` | `0.0..1.0` |
| `depth` | `1..5` (`MAX_CHAIN_DEPTH`) |
| `start` / `end` | ISO dates; `start <= end` |
| `name` / `topic` | non-empty |

## Models

### `Entity`

```json
{"id": "string", "name": "string", "type": "ORG | PERSON | LOCATION | POLICY | ..."}
```

### `Event`

```json
{
  "id": "string",
  "description": "string",
  "date": "YYYY-MM-DD",
  "date_key": 20513,
  "type": "string",
  "date_source": "explicit | inferred",
  "article_id": "string | null",
  "entities": [{"id": "string", "name": "string", "type": "string"}],
  "topics": ["string"]
}
```

### `Link`

```json
{
  "from_event_id": "string",
  "to_event_id": "string",
  "confidence": 0.9,
  "reason": "shared_entities+similar_topic",
  "from_date": "YYYY-MM-DD",
  "to_date": "YYYY-MM-DD"
}
```

### `Chain`

```json
{
  "query": {"entity_name": "string", "normalized_name": "string", "min_confidence": 0.0, "depth": 3, "limit": 100},
  "entity": {"id": "string", "name": "string", "type": "string"},
  "topic": null,
  "match_mode": "exact | case_insensitive_scan | none",
  "ambiguous": false,
  "events": [],
  "links": [],
  "truncated": false
}
```

### `Health`

```json
{
  "status": "ok | degraded",
  "neo4j": {
    "connected": true,
    "database": "neo4j",
    "server_version": "5.26.32",
    "edition": "community",
    "error": null
  }
}
```

## Error responses

| Status | Meaning |
|---|---|
| `404` | event id not found |
| `422` | request validation failed, or query rejected a bad range/parameter |
| `503` | Neo4j is not reachable; body is a degraded `Health` model |

## Notes and limitations

- Entity matching is exact and case-sensitive after normalization. `match_mode="case_insensitive_scan"`
  means the non-indexed fallback ran.
- Topic matching is exact; pipeline topics are lowercased.
- Year-only dates collapse to 1 January, so date-range results inherit that limitation.
- Live endpoint verification requires a configured `.env`; unit/API tests use an injected fake client.
- `starlette.testclient` currently reports an `httpx` deprecation warning; it is a dependency advisory, not
  an API behavior issue.
