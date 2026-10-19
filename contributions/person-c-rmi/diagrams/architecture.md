# Architecture diagram

Standalone Mermaid source for the Research/RMI lane. The same diagram is embedded in
[../ARCHITECTURE.md](../ARCHITECTURE.md).

```mermaid
flowchart LR
    K["Synthetic sorted keys<br/>NEW"] --> T["rmi.train<br/>NEW"]
    T --> M["Two-stage RMI<br/>NEW"]
    M --> L["Bounded lookup<br/>NEW"]
    L --> B["Benchmark harness<br/>NEW"]
    F["Injected fallback<br/>binary search now<br/>Neo4j later"] --> B
    B --> R["RESULTS.md<br/>NEW"]
    PB["Person B graph export<br/>BLOCKED until #8-#12 merge"] --> I["C4 integration<br/>BLOCKED"]
    F2["graphdb.queries fallback<br/>BLOCKED"] --> I

    classDef new fill:#eef3ff,stroke:#4b63a8,color:#1f2f5f;
    classDef blocked fill:#fff4e8,stroke:#b87333,color:#5f3a1f;
    class K,T,M,L,B,R new;
    class PB,F2,I blocked;
```

## Notes

- C1–C3 are independent of Person B.
- C4 requires Person B's PRs #8–#12 to merge first.
- The fallback is injected, so the benchmark harness does not import `graphdb` until C4.
