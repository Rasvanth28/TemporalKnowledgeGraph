# Person B — Graph DB & Backend session rules

These instructions apply to every OpenCode session working in this repository on the Graph DB & Backend
lane. Read this file first, then read [SESSION_HANDOFF.md](SESSION_HANDOFF.md). OpenCode sessions do not
remember each other; those files are the memory.

## 1. Authority and uncertainty

- The owner's explicit instruction in the current conversation overrides these defaults.
- Never assume permission. If an action is not clearly allowed, ask before doing it.
- Treat [PROPOSED], [ASSUMPTION], and [OPEN QUESTION] statements as unresolved.
- Never claim a command, test, index plan, or integration run succeeded without observed output.

## 2. Git safety

- Never commit, push, merge, rebase, force-push, switch branches, create branches, pull, or delete
  anything without explicit approval in the current conversation.
- Read-only commands are fine: `git status`, `git log`, `git diff`, `git branch -a`, `git remote -v`,
  `git fetch`.
- The remote is `origin`; the default branch is `main`. Confirm from git config rather than assuming.
- Work on `feature/<lane>-<short-desc>` branches created from an up-to-date `main`.
- Never commit to `main`.
- Stage files explicitly by path. Never use `git add .` or `git add -A`.
- Before every commit, show `git diff --staged --stat` and the full staged diff, then wait for approval.
- The owner opens Pull Requests unless they explicitly ask otherwise. Draft PR text in this contribution
  folder, not on GitHub.
- Never use `--force`, `--no-verify`, or bypass branch protection. If a push fails, report the exact error
  and propose a safe next step.

## 3. Secrets and environment

- Never commit `.env`.
- Never print, log, echo, or copy the Neo4j password or any API key.
- Never ask the owner to paste a secret into chat.
- `.env.example` contains placeholders only.
- Read connection settings from `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` using
  python-dotenv, like the existing code.
- No hardcoded credentials or URIs in code, tests, docs, or Compose files.
- Install dependencies only inside `.venv`, never system-wide.

## 4. Shared-file isolation

Do not edit these unless the owner explicitly approves that specific edit:

- root `README.md`
- `PROJECT_PLAN.md`
- `Documentation/`
- `common/schema.py`
- any `pipeline/` or `scripts/` file owned by Person A
- root `AGENTS.md`

Approved shared-file changes are limited to the current stage's explicit list. For Stage 1 they are:

- `requirements.txt` — append only new, installed, tested pins
- `.env.example` — add Neo4j placeholders
- `docker-compose.yml` — new optional alternative
- `.git/info/exclude` — add the local `opencode.json` only

Do not edit `.gitignore` for the local OpenCode config.

`common/schema.py` is a cross-team contract. If a change is needed, write an ADR and ask Person A to review;
do not edit it directly.

## 5. Documentation

- All lane documentation lives in `contributions/person-b-graphdb/`.
- Code lives in `graphdb/`; tests in `graphdb/tests/`.
- Keep relative links, descriptive filenames, and consistent Markdown.
- Do not duplicate shared docs; link to them.
- Update only documents affected by a change. Do not move or rewrite docs during development.
- Label claims as `[VERIFIED]`, `[ASSUMPTION]`, `[PROPOSED]`, or `[OPEN QUESTION]`.
- Never present inferred history as fact. ADRs remain `Proposed` until the owner accepts them.
- At the end of every session, rewrite `SESSION_HANDOFF.md` with status, last verified state, next step,
  open questions, files changed, and any uncommitted work.

## 6. Workflow for every task

### Phase A — Inspect

Read the relevant code, docs, git state, and environment. Do not trust summaries; verify.

### Phase B — Plan

For non-trivial work, report:

- problem and scope
- options and trade-offs
- risks
- tests and docs affected
- material decisions needing owner approval

Wait for approval before implementing.

### Phase C — Implement

- Small, reviewable steps.
- Follow existing conventions.
- No new dependency without approval.
- Keep changes focused; do not refactor Person A's code.
- If another lane's bug is found, report it rather than fixing it.

### Phase D — Verify

Run tests/linters, inspect `git diff`, and report exact results. Distinguish passed, failed, skipped, and
not executable. If a tool is unavailable, say so plainly.

### Phase E — Document and audit

Update only affected docs. Check every path, command, and link. Flag undocumented decisions and open
questions.

## 7. Graph backend rules

- Use parameterized Cypher only; never interpolate user/data values into query strings.
- Use `MERGE` on stable ids: `Article.id`, `Event.id`, `Entity.id`, `Topic.name`.
- Decide and document `ON CREATE SET` vs `ON MATCH SET` per property.
- Batch with `UNWIND` inside explicit transactions; record created/matched counts.
- Running the writer twice on identical input must leave identical counts.
- Keep Neo4j behind a small driver/session wrapper so tests can mock it.
- Store native Neo4j dates; use `date($param)` for ISO strings.
- `PRECEDES` is global `(date, id)` order and is rebuilt idempotently after each batch.
- `LINKED_TO` is latest-input-wins; do not delete stale links by default.
- Validate link endpoints against both the batch and existing graph; fail and roll back on missing ids.
- Query functions return plain Python dicts/dataclasses, never raw driver objects.
- Every chain query needs `min_confidence`, a depth cap, a result limit, and chronological ordering.
- Record edge confidence and reason on every relationship result.
- `events_in_date_range` and `event_by_id` are stable fallback contracts for Person C.

## 8. Testing rules

- Unit tests use a mocked driver and must always run.
- Integration tests use `@pytest.mark.integration` and auto-skip when `NEO4J_URI` is unset.
- Integration tests use only `test_`-prefixed ids and delete only those exact nodes.
- Never wipe the database; Aura free has one database.
- Run Person A's existing tests too and report regressions.
- Record exact commands and actual results in `TESTING.md`.
- Index-usage claims require `EXPLAIN`/`PROFILE` evidence.
- If something cannot run, record “could not execute” rather than inventing a result.

## 9. Stage gates

Each stage ends with a STOP for owner review. Do not start the next stage until the owner approves.
Do not commit or push merely because a stage is complete. Show the diff and wait.

Current stage sequence:

1. `feature/graphdb-foundation` — Stage 0 + Stage 1
2. `feature/graphdb-writer` — Stage 2
3. `feature/graphdb-queries` — Stage 3
4. `feature/graphdb-api` — Stage 4
5. `feature/graphdb-export-e2e` — Stage 5 + Stage 6

Each branch starts from an up-to-date `main` after the previous PR merges. Ask before stacking branches.

## 10. Accepted decisions

Read the ADRs before changing behavior:

- [ADR-0001](decisions/ADR-0001-neo4j-runtime-and-test-isolation.md)
- [ADR-0002](decisions/ADR-0002-graph-schema-and-temporal-semantics.md)
- [ADR-0003](decisions/ADR-0003-write-idempotency-and-validation.md)
- [ADR-0004](decisions/ADR-0004-query-api-and-export-contracts.md)

Accepted ADRs are not silently overridden. A change requires a new or superseding ADR and owner approval.
