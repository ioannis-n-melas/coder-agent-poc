# 0014 — Consolidate model-server to europe-west4

- **Status**: Accepted
- **Date**: 2026-04-21
- **Authors**: @ioannis-n-melas
- **Deciders**: @ioannis-n-melas
- **Supersedes (partial)**: [ADR-0011](0011-cloud-run-l4-gpu.md) — regional split only; all other decisions in ADR-0011 (L4 SKU, scale-to-zero, cold-start acceptance, GEN2 execution environment, GPU-mandatory sizing) remain in force.

## Context

[ADR-0011](0011-cloud-run-l4-gpu.md) placed the model-server in `us-central1` because, at time of writing, Cloud Run L4 GPU was not available in `europe-west4`. That ADR explicitly lists as a trigger to revisit: *"Cloud Run adds L4 support in `europe-west4` → consolidate back to primary region."*

The trigger has fired. Google's current [Cloud Run GPU documentation](https://cloud.google.com/run/docs/configuring/services/gpu) lists:

- `europe-west4` — **GA** for NVIDIA L4
- `us-central1` — **invitation only** (requires Google Account team)

This inverts ADR-0011's original rationale. `europe-west4` is now the self-serve path; `us-central1` would require a sales conversation and we'd still be off-region from [ADR-0004](0004-europe-west4-region.md).

Verified 2026-04-21 via `https://cloudquotas.googleapis.com/v1/projects/coder-agent-poc-2026/locations/global/services/run.googleapis.com/quotaInfos/NvidiaL4GpuAllocPerProjectRegion` — `applicableLocations` includes `europe-west4`, and Google's public GPU docs confirm GA status for that region.

## Options considered

### Option A — Keep `us-central1` (ADR-0011 status quo)
- Pros: no change required.
- Cons: `us-central1` is invitation-only — quota request needs a Google Account team conversation we don't have. `europe-west4` is now self-serve. Also: cross-region RTT (~100–130 ms per agent→model call) is pure loss now that co-location is available. Also: two AR repos + two regions = more infra surface.

### Option B — Consolidate to `europe-west4`
- Pros: self-serve quota path; co-located with `coder-agent` (eliminates cross-region RTT); collapses `var.model_server_region` into `var.region`; collapses the second AR repo into the primary one; restores ADR-0004's original intent (europe-west4 was chosen *specifically because* it was the EU region that supported GPU).
- Cons: none we've identified — this is the trigger ADR-0011 itself predicted.

### Option C — Move both services to `us-central1`
- Pros: would put everything in the most mature region.
- Cons: still invitation-only for GPU; inverts ADR-0004 for no benefit; higher latency for the EU-based developer.

## Decision

**Option B — consolidate `model-server` to `europe-west4`.**

One region (`var.region`), one Artifact Registry repository, one Cloud Run project configuration. The `var.model_server_region` variable and the `artifact_registry_gpu_region` module are removed. Scripts and env examples drop the `MODEL_SERVER_REGION` / `GPU_AR_HOST` split.

## Consequences

- **Good**: quota is self-serve (no Google sales conversation).
- **Good**: ~100–130 ms per agent→model hop goes away; agent loops get faster by multiples of that.
- **Good**: one AR repo (~$1.50/mo) instead of two.
- **Good**: fewer variables, fewer scripts branches, smaller blast radius for regional config errors.
- **Good**: ADR-0004's "europe-west4 because GPU later" intent is now fulfilled.
- **Neutral**: L4 cost profile unchanged (~$0.90/hr warm), cold-start window unchanged (~20–60 s), scale-to-zero unchanged.
- **Trigger to revisit**: (a) L4 capacity pressure in `europe-west4` that forces a fallback region, (b) need for a GPU SKU that isn't in `europe-west4` (none currently planned), (c) latency complaints from US users that justify a second US-region replica.

## References

- [ADR-0004 — Deploy to europe-west4](0004-europe-west4-region.md)
- [ADR-0011 — Cloud Run with NVIDIA L4 GPU for MVP serving](0011-cloud-run-l4-gpu.md) (regional decision superseded)
- [Cloud Run GPU regions (official docs)](https://cloud.google.com/run/docs/configuring/services/gpu)
