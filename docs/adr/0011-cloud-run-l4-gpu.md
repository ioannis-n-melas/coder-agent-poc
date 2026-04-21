# 0011 — Cloud Run with NVIDIA L4 GPU for MVP serving

- **Status**: Accepted
- **Date**: 2026-04-21
- **Authors**: @ioannis-n-melas
- **Deciders**: @ioannis-n-melas

## Context

The MVP model ([ADR-0013](0013-qwen3-coder-30b-a3b-instruct-model.md)) is Qwen3-Coder-30B-A3B-Instruct AWQ int4, which requires a GPU to serve at acceptable latency. The project has a hard constraint from [ADR-0001](0001-cloud-run-not-gke-for-poc.md): scale-to-zero must be preserved. That constraint rules out all options that require a minimum number of running nodes.

Cloud Run v2 (second-gen execution environment) now supports NVIDIA L4 GPU accelerators as a GA SKU, with `min-instances=0` supported. This is the only GA serverless GPU option on GCP that preserves true scale-to-zero.

The accepted trade-off going in: **cold start latency will be ~20–60 s** (CUDA image pull + model weight load + vLLM warmup). This is explicitly accepted and must not be treated as a regression in future sessions.

## Options considered

### Option A — Cloud Run v2 with NVIDIA L4 (1×, 24 GB VRAM)
- Pros: scale-to-zero preserved, no cluster to manage, L4 is the serverless GPU SKU on Cloud Run, stays within the Cloud Run operational model we already know.
- Cons: cold start ~20–60 s, L4 VRAM ceiling caps model size at roughly 24 GB loaded (AWQ int4 weights + KV cache), L4 availability limited to certain regions.

### Option B — GKE Autopilot + node pool with L4
- Pros: more flexible scheduling, node auto-provisioning can handle GPU nodes.
- Cons: breaks scale-to-zero (GKE Autopilot still has per-pod minimums and cluster overhead), adds GKE control plane cost, significantly higher operational complexity. This is the Phase 2 migration path, not the MVP path.

### Option C — Cloud Run v2 with A100 / H100
- Pros: more VRAM, faster decode.
- Cons: not available on Cloud Run — A100/H100 require GKE. Not a real option without abandoning Cloud Run.

### Option D — Vertex AI Prediction (dedicated endpoint)
- Pros: fully managed, GPU support.
- Cons: no scale-to-zero (charged per node-hour at minimum), less control over runtime and model format, does not compose cleanly with the vLLM deployment from [ADR-0010](0010-vllm-as-model-server-runtime.md).

## Decision

**Option A — Cloud Run v2, second-gen execution environment, 1× NVIDIA L4 (24 GB), `min-instances=0`.**

The scale-to-zero constraint is non-negotiable until there is a concrete RPS baseline justifying always-on cost. L4 on Cloud Run is the only option that satisfies both GPU and scale-to-zero.

Specifics:
- Execution environment: second-gen (required for GPU on Cloud Run).
- GPU: 1× NVIDIA L4 (24 GB VRAM).
- `min-instances: 0`, `max-instances: 1` (MVP — no horizontal scaling yet).
- Primary region: `us-central1` (L4 availability confirmed). See ADR-0004 for the europe-west4 context — L4 is not available in europe-west4 as of 2026-04. This is a regional deviation for the GPU service only.
- Fallback region: `us-east1` (document in Terraform variables, not hardcoded).
- Cold start: ~20–60 s. Acceptable for MVP. **Not a bug, not a regression.**

## Consequences

- **Good**: scale-to-zero is preserved — zero cost when idle.
- **Good**: stays on Cloud Run; operational model unchanged from POC.
- **Good**: no cluster to manage.
- **Bad**: cold starts are significant (~20–60 s). Users hitting a cold instance will experience a long first-token delay. Mitigation strategies (pre-warm endpoint, keep-alive pings) are deferred to a later decision.
- **Bad**: L4 VRAM ceiling (24 GB) caps model size. Any model that exceeds ~20 GB loaded (weights + KV cache at chosen `max_model_len`) cannot run here without switching to GKE for a multi-GPU node.
- **Bad**: L4 availability is not in `europe-west4` (the project's home region per [ADR-0004](0004-europe-west4-region.md)). The model server will run in a different region from the agent until Cloud Run GPU expands regionally — adds cross-region latency and egress cost.
- **Trigger to revisit**: (a) sustained traffic justifies `min-instances=1` to eliminate cold starts — write an ADR with the cost/latency trade-off, (b) model size requirements exceed L4 VRAM budget → migrate GPU service to GKE with multi-GPU node pool, (c) Cloud Run adds L4 support in `europe-west4` → consolidate back to primary region.

## References

- [ADR-0001 — Cloud Run, not GKE+KServe, for Phase 1](0001-cloud-run-not-gke-for-poc.md)
- [ADR-0004 — Deploy to europe-west4](0004-europe-west4-region.md)
- [ADR-0010 — vLLM as model server runtime](0010-vllm-as-model-server-runtime.md)
- [ADR-0013 — Qwen3-Coder-30B-A3B-Instruct as MVP model](0013-qwen3-coder-30b-a3b-instruct-model.md)
- [Cloud Run GPU documentation](https://cloud.google.com/run/docs/configuring/services/gpu)
- [NVIDIA L4 GPU specs](https://www.nvidia.com/en-us/data-center/l4/)
