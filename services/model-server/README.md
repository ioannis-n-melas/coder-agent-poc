# model-server

llama.cpp serving Qwen2.5-Coder-1.5B-Instruct (Q4_K_M GGUF) on Cloud Run, CPU-only.

## OpenAI-compatible endpoints

```
GET  /health
POST /v1/chat/completions
POST /v1/completions
POST /v1/embeddings            # not configured on this model
GET  /v1/models
```

## Local run

```bash
# From repo root
docker build -t model-server:dev services/model-server
docker run --rm -p 8080:8080 model-server:dev

# In another terminal
curl -s http://localhost:8080/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"qwen","messages":[{"role":"user","content":"Write a Python hello world"}],"max_tokens":64}' | jq
```

## Swap the model

Edit the `Dockerfile` `ARG MODEL_HF_REPO` / `ARG MODEL_FILE`, rebuild. For an ADR-worthy change, write a new ADR superseding `docs/adr/0008-qwen25-coder-15b-model.md`.

## Cloud Run sizing

2 vCPU / 4 GiB memory / min=0 / max=2. See `infra/terraform/variables.tf` for overrides.

## Cold-start notes

- Image pull: ~10–20 s (~1.5 GiB compressed).
- llama.cpp mmap: ~5–10 s.
- Total: budget 30 s for the first request after idle.

If the cold start becomes a blocker, options in priority order:
1. Smaller quant (Q3_K_S) — ~700 MB, lower quality.
2. `min_instances=1` on Cloud Run (~$10–30/mo, but no cold starts).
3. Switch to GKE + KServe with pre-warmed replicas (Phase 2).
