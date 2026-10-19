# PR 0004 — Thin FastAPI query layer

- **Base branch:** `feature/graphdb-queries` (stacked; retarget to `main` after the earlier PRs merge)
- **Head branch:** `feature/graphdb-api`
- **PR scope:** Stage 4
- **Suggested title:** `feat: add FastAPI query layer`

## Summary

Adds the stable HTTP contract over `graphdb/queries.py`:

- `GET /health` with `503` degraded response;
- `GET /events/{event_id}` with `404`;
- `GET /events?start=&end=&limit=&offset=`;
- `GET /chains/entity`, `/chains/topic`, `/chains/date-range`;
- Pydantic response models, validation limits, and OpenAPI at `/openapi.json`;
- `contributions/person-b-graphdb/api/` with the contract, curl examples, and a Postman collection.

Route handlers contain no graph logic; they call the stable query functions.

## Test results

```text
pytest graphdb/tests/test_api.py            10 passed
pytest graphdb/tests -m "not integration"   58 passed, 3 deselected
pytest -q                                   100 passed, 3 skipped, 1 warning
pip check                                   No broken requirements found.
compileall graphdb                          exit 0
```

The warning is Starlette's test-client `httpx` deprecation advisory. It is not an API failure.

## Known limitations

- Live endpoints are not exercised against Aura yet.
- `depth` is capped at `MAX_CHAIN_DEPTH` (5).
- Entity case-insensitive fallback is a non-indexed scan.
- Year-only dates remain a query limitation.

## Review focus

1. `graphdb/api.py` — startup/lifespan, dependency injection, route validation.
2. `graphdb/tests/test_api.py` — health, all query routes, 404, 422, OpenAPI.
3. `contributions/person-b-graphdb/api/API_CONTRACT.md` — stable models and error contract.
4. `api/postman_collection.json` and `api/curl_examples.md` — consumer examples.
