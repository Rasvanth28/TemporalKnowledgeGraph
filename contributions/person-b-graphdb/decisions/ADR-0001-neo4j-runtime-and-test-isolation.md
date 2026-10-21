# ADR-0001 — Neo4j runtime, configuration, and test isolation

- **Status:** Accepted
- **Decision date:** 2026-10-19

## Context

The Graph DB & Backend lane needs a real Neo4j instance for schema, writer, query, and integration tests.
The project plan recommends Aura free to avoid local setup, while the proposed repository structure also
mentions `docker-compose.yml` as an alternative.

The current development shell has Python 3.14 and no working Docker CLI. Docker Desktop may be partially
installed, but it is not usable from this shell. No Aura instance or `.env` existed at the start of the
work. [VERIFIED]

Aura free gives the project one database, so integration tests cannot assume a disposable database.

## Requirements and constraints

- Use Aura free as the working instance.
- Provide `docker-compose.yml` as a documented alternative.
- Label Compose “untested” if it cannot be executed.
- Read credentials from `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` with python-dotenv.
- Never commit `.env`, print the password, or hardcode credentials.
- Integration tests use ids prefixed with `test_` and delete only those exact nodes.
- Never wipe or reset the database.
- Integration tests auto-skip when `NEO4J_URI` is unset.

## Alternatives considered

1. **Aura only.** Simplest, matches the project plan, but there is no local fallback and tests need network
   access plus the owner-created instance.
2. **Docker Compose only.** Reproducible and local, but blocked on installing/starting Docker; would delay
   the lane.
3. **Aura primary plus Compose alternative.** Unblocks implementation with the recommended platform and
   still gives the team a reproducible local option when Docker is available.
4. **A disposable test database.** Rejected because Aura free provides one database and the owner
   explicitly forbade wiping it.

## Decision

Use **Aura free** as the working instance and provide a **Docker Compose alternative** at the repository
root. The Compose file is pinned to `neo4j:5.26.32-community`, reads credentials from `.env`, and is clearly
labeled untested until someone runs it.

Connection settings are environment-only. The local `.env` is never committed, read into logs, or echoed.
The `NEO4J_DATABASE` default is `neo4j`.

Integration tests use the same single database with a `test_` id namespace. Each test deletes only the
exact ids it created, in `finally`. No test may run a broad delete or database reset. If `NEO4J_URI` is
unset, integration tests skip and the skip is recorded as a skip, not a pass.

## Reasons

- Aura matches `PROJECT_PLAN.md`'s Day 0 recommendation and avoids a Docker installation blocker.
- Compose preserves the documented local alternative without pretending it was verified.
- Namespaced ids are the only safe isolation strategy on a single free database.
- Environment-only configuration keeps secrets out of git and supports both Aura and local Compose.

## Consequences and trade-offs

- Stage 1 integration evidence requires the owner to create the Aura instance and fill `.env`.
- The Compose path may drift or fail unnoticed until Docker is available and the file is executed.
- Tests share one database and must be written defensively; broad cleanup is forbidden.
- Aura network/TLS failures must be reported as environment failures, not hidden as test skips when
  `NEO4J_URI` is set.

## Evidence

- `PROJECT_PLAN.md` recommends Aura free to avoid local setup pain. [VERIFIED]
- The current shell has no Docker CLI on `PATH`; `C:\ProgramData\DockerDesktop` exists and WSL lists a
  stopped `docker-desktop` distro, but Docker is not usable. [VERIFIED]
- No `.env` existed at inspection time. [VERIFIED]
- The Docker Hub tag `5.26.32-community` was observed in the registry listing. [VERIFIED]
- Aura has not yet been reached; no connection result is claimed. [OPEN QUESTION]

## Conditions to revisit

- Docker becomes available and the Compose file is actually tested.
- Aura free limits or quotas block the test approach.
- The project obtains a disposable database or a second instance.
- Integration tests become slow or interfere with each other despite the `test_` namespace.
