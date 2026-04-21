# 0004 — Deploy to europe-west4

- **Status**: Accepted
- **Date**: 2026-04-19
- **Authors**: @ioannis-n-melas

## Context

Our other GCP work (market-snapshot) runs in `europe-west2` (London). We want to optionally add Cloud Run GPU later, which is limited to specific regions.

## Options considered

### Option A — europe-west2 (London)
- Pros: co-located with existing work, lower latency for UK users.
- Cons: **no Cloud Run GPU** in this region as of 2026-04. Forces us to change region if we add GPU.

### Option B — europe-west4 (Netherlands)
- Pros: supports Cloud Run GPU (L4). Similar cost to europe-west2. Low latency to UK/EU.
- Cons: not co-located with market-snapshot (not a concern for this standalone project).

### Option C — us-central1
- Pros: most mature GCP region, cheapest for many services.
- Cons: higher latency for EU users, data residency considerations.

## Decision

**Option B — europe-west4.** Lets us add Cloud Run GPU later without re-regionalizing the project.

## Consequences

- **Good**: GPU path unblocked for Phase 1 evolution (still on Cloud Run, just enable GPU).
- **Bad**: Slightly higher latency to UK vs. London.
- **Trigger to revisit**: (a) latency complaints from users, (b) data residency requirement for UK-only data (would force `europe-west2`).

## References

- [Cloud Run GPU region availability](https://cloud.google.com/run/docs/configuring/services/gpu#regions)
