# Architecture diagram

Mermaid source for the Graph DB & Backend lane. The same diagram is embedded in
[../ARCHITECTURE.md](../ARCHITECTURE.md).

```mermaid
flowchart LR
    A["Person A<br/>pipeline_output.json<br/>PipelineOutput objects"] --> B["graphdb.writer<br/>NEW<br/>MERGE + batching"]
    B --> C[("Neo4j<br/>NEW instance<br/>Aura primary / Compose fallback")]
    C --> D["graphdb.queries<br/>NEW<br/>stable contract"]
    C --> E["graph-to-flat export<br/>NEW"]
    D --> F["graphdb.api<br/>NEW<br/>FastAPI"]
    F --> G["Postman / curl / future frontend<br/>NEW"]
    E --> H["Person C RMI<br/>REUSED consumer<br/>fallback + training keys"]
    C --> I["Neo4j B+ tree indexes<br/>REUSED database capability"]

    classDef reused fill:#eef7ee,stroke:#4b7f4b,color:#1f3d1f;
    classDef new fill:#eef3ff,stroke:#4b63a8,color:#1f2f5f;
    class A,H,I reused;
    class B,C,D,E,F,G new;
```

## Legend

- **REUSED** — existing project or database capability; this lane consumes it without changing it.
- **NEW** — implemented or configured by this lane.

## Notes

- Aura is the working Neo4j instance; Docker Compose is a documented but currently untested alternative.
- The writer consumes both `PipelineOutput` objects and the JSON shape from `pipeline/export.py`.
- Person C consumes both `graphdb/queries.py` and the flat event-key export.
- The API is a thin layer over `queries.py`; it does not contain graph logic.
