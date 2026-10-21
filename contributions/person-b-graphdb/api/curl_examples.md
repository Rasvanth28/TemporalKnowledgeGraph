# API curl examples

Start the API inside `.venv` after the Neo4j environment is configured:

```powershell
python -m graphdb.api
# or
uvicorn graphdb.api:app --host 127.0.0.1 --port 8000
```

Set a local base URL if you are not using the default:

```powershell
$Base = "http://127.0.0.1:8000"
```

## Health

```powershell
curl "$Base/health"
```

## Event by id

```powershell
curl "$Base/events/test_fixture_evt_1"
```

## Events in a date range

```powershell
curl --get "$Base/events" --data-urlencode "start=2026-01-01" --data-urlencode "end=2026-12-31"
```

## Entity chain

```powershell
curl --get "$Base/chains/entity" `
  --data-urlencode "name=Test Fixture Bank" `
  --data-urlencode "min_confidence=0.5" `
  --data-urlencode "depth=3" `
  --data-urlencode "limit=100"
```

## Topic chain

```powershell
curl --get "$Base/chains/topic" `
  --data-urlencode "topic=test-fixture interest rates" `
  --data-urlencode "min_confidence=0.0" `
  --data-urlencode "depth=3" `
  --data-urlencode "limit=100"
```

## Date-range chain

```powershell
curl --get "$Base/chains/date-range" `
  --data-urlencode "start=2026-01-01" `
  --data-urlencode "end=2026-03-31" `
  --data-urlencode "min_confidence=0.0" `
  --data-urlencode "depth=3" `
  --data-urlencode "limit=100"
```

## OpenAPI

```powershell
curl "$Base/openapi.json"
```

No credentials or Neo4j password are ever sent to the API; the API reads them from the server-side
environment.
