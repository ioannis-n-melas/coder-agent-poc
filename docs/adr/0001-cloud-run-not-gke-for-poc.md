# 0001 — Cloud Run, not GKE+KServe, for Phase 1

- **Status**: Accepted
- **Date**: 2026-04-19
- **Authors**: @ioannis-n-melas
- **Deciders**: @ioannis-n-melas

## Context

The reference article ([Schneider, 2026](https://medium.com/@mrschneider/a-kubernetes-native-coder-agent-deepagent-kserve-self-hosted-llms-59e829e3be7d)) deploys a coder agent on **GKE + KServe**. The client constraints for this project are:

- Scale-to-zero idle cost
- No GPU required for POC
- Easy to launch, easy to iterate
- Low cost, upgradeable later

GKE Standard has a ~$73/mo control-plane cost even when empty. GKE Autopilot has lower floor but still per-pod charges. KServe's ingress and autoscaler add complexity.

## Options considered

### Option A — GKE Autopilot + KServe
- **Pros**: matches the article directly, true Kubernetes story from day one, vLLM works well, path to GPU via Node Auto-Provisioning.
- **Cons**: baseline cost > $0, slower to iterate (cluster ops), more YAML per deploy, ingress and TLS complexity.

### Option B — Cloud Run + llama.cpp (or vLLM)
- **Pros**: true scale-to-zero, single-line deploy, no cluster to manage, free when idle, supports GPU (L4) in a few regions if we need it, HTTP contract identical to KServe's OpenAI endpoint.
- **Cons**: cold start on the model server (~10 s for Qwen-1.5B Q4), diverges from the article's stack, single-region by default.

### Option C — Vertex AI endpoints
- **Pros**: fully managed, good Google integration.
- **Cons**: pricing is per-node-hour (no true scale-to-zero), less control over runtime, no clean self-hosted-model story.

## Decision

**Go with Option B: Cloud Run for Phase 1.**

The **agent ↔ model contract is OpenAI-compatible HTTP**, regardless of backend. This means the Phase 2 migration to GKE+KServe is a **URL swap plus a new Terraform module** — no agent code change. We get POC velocity now without burning the bridge.

## Consequences

- **Good**: idle cost = $0. Deploy = one `gcloud run deploy` or one `terraform apply`. Reasoning about scaling is trivial.
- **Good**: the architectural invariant ("agent talks to an OpenAI-compatible endpoint") is forced by this choice, which is exactly what we want for portability.
- **Bad**: the POC will not teach us about KServe operational quirks. We pay that learning cost in Phase 2.
- **Bad**: cold starts visible to users until we either add min-instances (cost) or pre-warm.
- **Trigger to revisit**: any of — (a) sustained RPS justifies min-instances of ≥ 1 for several services, (b) need GPU runtime that Cloud Run GPU can't serve in `europe-west4`, (c) multi-tenant isolation requires cluster-level boundaries, (d) integration with existing GKE-based internal services.

## References

- [Reference article — Schneider, "A Kubernetes-Native Coder Agent"](https://medium.com/@mrschneider/a-kubernetes-native-coder-agent-deepagent-kserve-self-hosted-llms-59e829e3be7d)
- [Cloud Run vs GKE decision tree (GCP docs)](https://cloud.google.com/run/docs/fit-for-run)
- ADR [0002 — llama.cpp as POC model server](0002-llama-cpp-for-poc-model-server.md)
