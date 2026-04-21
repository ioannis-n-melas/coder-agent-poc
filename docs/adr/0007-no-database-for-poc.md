# 0007 — No database for the POC

- **Status**: Accepted
- **Date**: 2026-04-19
- **Authors**: @ioannis-n-melas

## Context

market-snapshot uses Cloud SQL (Postgres) for persistent state. For this POC we need to decide whether to include a database from the start.

## Options considered

- **Cloud SQL from day one** — familiar pattern, but has a ~$10/mo floor and adds schema/migration complexity.
- **Firestore (serverless NoSQL)** — scales to zero, but schema drift is a pain.
- **Cloud Storage for artifacts** — fine for files; not a DB.
- **No persistence at all** — stateless agent; all session state in the request.

## Decision

**No database for POC.** The agent is stateless. Any artifacts (generated code, run traces) go to a Cloud Storage bucket with TTL'd lifecycle rules.

## Consequences

- **Good**: one less moving part, zero idle cost, no migrations to maintain.
- **Bad**: no conversation history across requests — every request is fresh context.
- **Trigger to revisit**: (a) multi-turn conversations required, (b) need to audit past agent runs, (c) need user sessions/authentication with per-user state.

## References

- [Cloud SQL pricing](https://cloud.google.com/sql/pricing)
- [Cloud Storage lifecycle rules](https://cloud.google.com/storage/docs/lifecycle)
