# 0010 — vLLM as model server runtime

- **Status**: Accepted — supersedes [#0002](0002-llama-cpp-for-poc-model-server.md)
- **Date**: 2026-04-21
- **Authors**: @ioannis-n-melas
- **Deciders**: @ioannis-n-melas

## Context

ADR-0002 chose llama.cpp for the POC model server because the POC ran on CPU and needed a small container, fast cold start, and scale-to-zero. Those constraints are still present, but the balance shifts when moving to MVP on GPU:

- GPU inference is the primary target. vLLM's PagedAttention and continuous batching are designed for this; llama.cpp's GPU path is a secondary concern.
- The MVP model ([ADR-0013](0013-qwen3-coder-30b-a3b-instruct-model.md)) is Qwen3-Coder-30B-A3B-Instruct AWQ — a HuggingFace-native weight format. llama.cpp requires GGUF conversion, which is an extra build-time step and is not the community-maintained primary format for AWQ models.
- vLLM natively exposes an OpenAI-compatible HTTP server, preserving the agent ↔ model contract established in [ADR-0001](0001-cloud-run-not-gke-for-poc.md).

The forcing trigger listed in ADR-0002 was satisfied: "we move to GPU and want vLLM."

## Options considered

### Option A — vLLM
- Pros: production-standard GPU runtime, PagedAttention, continuous batching, first-class AWQ/GPTQ support, native OpenAI-compatible server, large and active ecosystem.
- Cons: CUDA base image (~5–10 GiB), cold start increases (CUDA init + model load + vLLM warmup adds ~20–60 s), GPU-only in practice (CPU path exists but is not a first-class use case).

### Option B — Keep llama.cpp (GGUF + CUDA backend)
- Pros: smaller image, can fall back to CPU.
- Cons: GGUF conversion step for every model update, GPU perf inferior to vLLM on same hardware, AWQ is a second-class path, less community investment in GPU optimisation.

### Option C — SGLang
- Pros: strong RadixAttention (KV cache reuse), competitive throughput on some workloads.
- Cons: smaller ecosystem, less battle-tested, fewer model-specific workarounds for edge cases, more uncertain long-term maintenance.

### Option D — TGI (HuggingFace Text Generation Inference)
- Pros: mature, HuggingFace first-party.
- Cons: OpenAI compatibility is a compatibility shim rather than native; historically behind vLLM on feature parity for agentic/tool-use workloads; quantisation support less flexible.

## Decision

**Option A — vLLM.** Mature, GPU-first, natively OpenAI-compatible, strong AWQ support. SGLang is worth watching but loses on ecosystem maturity for an MVP that has to be supportable.

Specifics:
- Base image: `vllm/vllm-openai` (CUDA 12.x), pinned to a release tag in Dockerfile.
- Served via `python -m vllm.entrypoints.openai.api_server`.
- Quantization: AWQ int4 (passed via `--quantization awq`).
- The `--served-model-name` matches the name the agent passes, satisfying ADR-0001's URL-swap portability.

## Consequences

- **Good**: agent code is entirely unaffected — same OpenAI-compatible HTTP contract ([ADR-0001](0001-cloud-run-not-gke-for-poc.md)).
- **Good**: AWQ models load natively, no conversion step.
- **Good**: continuous batching and PagedAttention enable higher throughput at MVP scale.
- **Bad**: CUDA image is large; cold starts rise to ~20–60 s (documented further in [ADR-0011](0011-cloud-run-l4-gpu.md)).
- **Bad**: no CPU fallback. If GPU capacity is unavailable in a region, the service is down, not degraded.
- **Bad**: build pipeline requires CUDA toolchain and a GPU runner or multi-stage cross-build to avoid building on CPU.
- **Trigger to revisit**: (a) SGLang closes the ecosystem gap and benchmarks show >20 % throughput improvement on the MVP workload, (b) we need tensor parallelism across multiple GPUs (vLLM supports this, but the Cloud Run deployment model would need to change), (c) vLLM drops support for a quantization scheme we need.

## References

- [ADR-0001 — Cloud Run, not GKE+KServe, for Phase 1](0001-cloud-run-not-gke-for-poc.md)
- [ADR-0002 — llama.cpp as the POC model server](0002-llama-cpp-for-poc-model-server.md) (superseded by this ADR)
- [ADR-0011 — Cloud Run with NVIDIA L4 GPU for MVP serving](0011-cloud-run-l4-gpu.md)
- [ADR-0013 — Qwen3-Coder-30B-A3B-Instruct as MVP model](0013-qwen3-coder-30b-a3b-instruct-model.md)
- [vLLM documentation](https://docs.vllm.ai/)
- [vLLM OpenAI-compatible server](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html)
