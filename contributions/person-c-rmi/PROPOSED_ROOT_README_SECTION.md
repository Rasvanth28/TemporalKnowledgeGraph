# Proposed root README section — Research/RMI

> **Status: [PROPOSED].** Do not paste into the root `README.md` until the team consolidates after review.

## RMI research lane (Person C)

The RMI lane investigates whether a learned index can answer date-key lookups faster than Neo4j's B+ tree
index, with a guaranteed-correct fallback to Neo4j.

### Run the independent core

```powershell
python -m pytest rmi/tests -q
python -m rmi.train --keys 10000 --distribution uniform --seed 42
```

Configuration:

```dotenv
RMI_STAGE_MODELS=linear,linear
RMI_BUCKET_COUNT=128
```

### What is implemented now

- Two-stage RMI with config-driven stage models and bucket count.
- Maximum-training-error correction windows guaranteeing all training keys are found.
- Synthetic uniform and clustered sorted-key generators.
- Idempotent `retrain_rmi()` entry point.

### Blocked until Person B merges

The live RMI-vs-B+tree benchmark needs Person B's `graphdb/queries.py` fallback and a reachable Neo4j
instance. Until then, benchmark numbers are synthetic and marked as such.

See `contributions/person-c-rmi/` for decisions, testing evidence, and `RESULTS.md`.
