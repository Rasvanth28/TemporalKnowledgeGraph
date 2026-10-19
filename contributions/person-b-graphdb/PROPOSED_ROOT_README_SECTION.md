# Proposed root README section — Graph DB & Backend

> **Status: [PROPOSED].** Do not paste this into the root `README.md` until the owner and the team approve.
> The root README is intentionally untouched during development.

## Graph DB & Backend (Person B lane)

The graph lane loads Person A's pipeline output into Neo4j and exposes event-chain queries for the API and
Person C's RMI fallback.

### 1. Choose a Neo4j instance

**Aura free (recommended):**

1. Create a Neo4j Aura free instance in the Neo4j console.
2. Copy the connection URI; it normally starts with `neo4j+s://`.
3. Put the URI, user, password, and database in your local `.env`. Do not commit `.env`.

```dotenv
NEO4J_URI=neo4j+s://<instance-id>.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<your-password>
NEO4J_DATABASE=neo4j
```

**Docker Compose alternative (untested on the current machine):**

```powershell
# Fill NEO4J_USER and NEO4J_PASSWORD in .env first.
docker compose up -d
```

The Compose file exposes Neo4j on `bolt://localhost:7687` and the browser on `http://localhost:7474`.
Docker was not available in the development shell, so this path is documented but not verified here.

### 2. Install Python dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 3. Check the connection

```powershell
python -m graphdb.health
```

This prints the database, server version, and connection status. It never prints the password.

### 4. Apply indexes and constraints

```powershell
python -m graphdb.apply_schema
python -m graphdb.apply_schema --verify-only
```

The script is rerunnable. It applies the four design-document indexes and the approved uniqueness
constraints, then verifies the resulting schema objects with `SHOW INDEXES`.

### 5. Run tests

```powershell
python -m pytest
python -m pytest graphdb/tests -m "not integration"
python -m pytest graphdb/tests -m integration
```

Integration tests require `NEO4J_URI` and use only `test_`-prefixed ids. They never wipe the database.

### 6. Query and API status

`graphdb/queries.py` and `graphdb/api.py` are later stages. Once available, the API will expose:

- `/health`
- entity, date-range, and topic chain queries
- flat event lookup helpers for the RMI fallback

The exact endpoint contract will be documented before implementation.

### Known limitations

- Year-only dates are stored as 1 January, so date ranges that start after 1 January can miss them.
- Old `LINKED_TO` relationships are not deleted by a later run with a different corpus.
- Global `PRECEDES` edges are rebuilt after each write batch; this is a batch-oriented design.

See `contributions/person-b-graphdb/` for the design, decisions, testing evidence, and review guide.
