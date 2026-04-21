# 0002 — llama.cpp as the POC model server

- **Status**: Accepted
- **Date**: 2026-04-19
- **Authors**: @ioannis-n-melas

## Context

We need to serve Qwen2.5-Coder-1.5B-Instruct on Cloud Run with CPU only, scale-to-zero, and expose an OpenAI-compatible HTTP API so the agent code is portable.

## Options considered

### Option A — vLLM
- Pros: industry standard, great GPU perf, native OpenAI API, wide model support.
- Cons: **GPU-first**. CPU support exists but is a second-class path. Container is heavy (~5 GiB). Cold start on CPU is ~30–60 s.

### Option B — llama.cpp (server mode)
- Pros: small container (~100 MB + model), excellent CPU perf on quantized GGUF, fast cold start (~5–15 s), OpenAI-compatible endpoints built in, actively maintained.
- Cons: GGUF format differs from HuggingFace format — Phase 2 GPU migration to vLLM requires re-downloading weights (but the URL contract holds).

### Option C — Ollama
- Pros: very easy to use, OpenAI-compatible.
- Cons: bigger base image, extra daemon layer, less direct control for production serving.

### Option D — llama-cpp-python
- Pros: Python-native, easy to extend.
- Cons: slower than native llama.cpp, more moving parts, GIL contention under load.

## Decision

**Option B — llama.cpp server.** Best fit for CPU + small model + scale-to-zero. The OpenAI-compatible endpoint preserves the portability story.

Specifics:
- Image: `ghcr.io/ggml-org/llama.cpp:server` (pinned to a release tag in Dockerfile).
- Model format: GGUF Q4_K_M.
- Context size: 8192 (enough for code-in + plan + code-out; adjustable).
- Model baked into the container image at build time — simpler than GCS-fuse mount for POC. Swappable via build args.

## Consequences

- **Good**: Fast iteration on model choice — rebuild image with different `MODEL_URL` build arg.
- **Good**: Image stays under 2 GiB; well under Cloud Run's 10 GiB limit.
- **Bad**: Changing the model requires a rebuild + redeploy. If this becomes a bottleneck, move to GCS-fuse mounted weights.
- **Bad**: On Phase 2 (GPU), we swap runtimes anyway — llama.cpp does run on GPU but vLLM wins by a wide margin for production.
- **Trigger to revisit**: (a) we move to GPU and want vLLM, (b) throughput needs exceed what llama.cpp gives us (~100 tok/s on L4 vs. 400+ for vLLM), (c) we want features vLLM has and llama.cpp doesn't (LoRA hot-swap, tensor parallelism).

## References

- [llama.cpp server docs](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [OpenAI API compatibility — llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#openai-api-compatibility)
- ADR [0008 — Qwen2.5-Coder-1.5B as POC model](0008-qwen25-coder-15b-model.md)
