# Person C — Research/RMI session rules

These instructions apply to sessions working on the Research/RMI lane. Read this file and
[SESSION_HANDOFF.md](SESSION_HANDOFF.md) first.

## 1. Lane boundaries

- Code lives in `rmi/`; tests in `rmi/tests/`.
- Documentation lives in `contributions/person-c-rmi/`.
- Branch from `origin/main`; do not branch from Person B's `feature/graphdb-*` branches.
- Do not edit `graphdb/`, `common/schema.py`, `pipeline/`, `scripts/`, root `README.md`, or
  `PROJECT_PLAN.md`.
- Do not edit shared `requirements.txt` or `.env.example` unless explicitly approved; `numpy` and
  `scikit-learn` are already pinned.
- The final integration PR may import `graphdb.queries` only after Person B's PRs merge.

## 2. Git and PR rules

- Never commit, push, merge, rebase, force-push, or switch branches without explicit approval.
- Feature branches follow `feature/rmi-<short-desc>`.
- Stage by explicit path only; never `git add .` or `git add -A`.
- Before a commit, show the staged stat and full staged diff.
- The owner opens/merges PRs unless asked otherwise; draft PR descriptions in `pr/`.
- Keep each PR review-sized and state any PR dependency in its description.

## 3. RMI rules

- Stage count and per-stage model type come from config, not hardcoded callers.
- Keys are sorted, unique integers.
- Compute stage-2 maximum training error and size the correction window from it.
- Out-of-range or unmatched predictions must report fallback, never a wrong index.
- Keep the fallback injectable; do not import `graphdb` at module level in the core.
- `retrain_rmi()` must be idempotent and manually triggerable.
- Benchmark RMI and fallback on the same query set.
- Report negative results honestly.

## 4. Testing and docs

- Unit tests must run without Neo4j.
- Integration tests use `@pytest.mark.integration` and auto-skip without `NEO4J_URI`.
- Record exact commands and actual results in `TESTING.md`.
- Label claims `[VERIFIED]`, `[ASSUMPTION]`, `[PROPOSED]`, or `[OPEN QUESTION]`.
- Update only affected docs. Rewrite `SESSION_HANDOFF.md` at the end of every session.

## 5. Stage gates and dependencies

- C1: `feature/rmi-core` — RMI core. No Person B dependency.
- C2: `feature/rmi-benchmark` — benchmark with injected fallback. Depends on C1.
- C3: `feature/rmi-drift` — retrain/drift experiment and RESULTS draft. Depends on C2.
- C4: `feature/rmi-neo4j-integration` — **blocked until Person B PRs #8–#12 merge and Aura `.env` exists.**

If Person B review feedback or Aura verification becomes available, Person B takes priority over C work.

## 6. Accepted decisions

- [ADR-0001](decisions/ADR-0001-rmi-model-config-and-error-bounds.md)
- [ADR-0002](decisions/ADR-0002-fallback-benchmark-contract.md)
- [ADR-0003](decisions/ADR-0003-retrain-drift-experiment.md)
