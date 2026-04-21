# model-server

vLLM serving **Qwen3-Coder-30B-A3B-Instruct (AWQ int4)** on an NVIDIA L4 GPU via
Cloud Run. OpenAI-compatible HTTP — the agent sees no difference between this
and any other `/v1/chat/completions` backend ([ADR-0001][adr-0001]).

Runtime: vLLM ([ADR-0010][adr-0010]). Target platform: Cloud Run v2 + 1× L4,
scale-to-zero ([ADR-0011][adr-0011]). Model: Qwen3-Coder-30B-A3B-Instruct AWQ
int4 ([ADR-0013][adr-0013]).

## OpenAI-compatible endpoints

```
GET  /health                    # 200 when the model is loaded and ready
GET  /v1/models                 # lists the served model id
POST /v1/chat/completions       # the agent's request path (streaming + non-streaming)
POST /v1/completions
```

The agent calls `openai.OpenAI(base_url="$MODEL_SERVER_URL/v1")` with
`model="Qwen/Qwen3-Coder-30B-A3B-Instruct"`. That model id is the
`--served-model-name` flag in [`entrypoint.sh`](./entrypoint.sh); it is
deliberately independent of the underlying AWQ HF repo so that swapping
between community AWQ builds never breaks the agent.

## Building

```bash
docker build -t model-server:dev services/model-server
```

The build has two stages:

1. **weight-downloader** — pulls the AWQ int4 shards from HuggingFace using
   `hf_transfer` (parallel-chunked download). Weights are baked into the
   runtime image; see [`scripts/fetch_weights.py`](./scripts/fetch_weights.py)
   for why that decision was made.
2. **runtime** — `vllm/vllm-openai:v0.19.1-ubuntu2404` with the baked weights
   copied in and a non-root user wired up.

If you need to pull from a gated HF repo, pass a token via Docker secret
(never via `--build-arg`, never via an `ENV`):

```bash
echo -n "$HF_TOKEN" > /tmp/hf_token
docker build \
  --secret id=hf_token,src=/tmp/hf_token \
  -t model-server:dev services/model-server
rm /tmp/hf_token
```

## Running locally

Requires a host with an NVIDIA GPU and the NVIDIA Container Toolkit
installed. On Apple Silicon laptops this won't work — run against a deployed
Cloud Run instance instead (see the "Live contract tests" section below).

```bash
docker run --rm --gpus all -p 8080:8080 \
  -e PORT=8080 \
  model-server:dev

# In another terminal:
curl -s http://localhost:8080/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{
    "model": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
    "messages": [{"role":"user","content":"Write a Python hello world"}],
    "max_tokens": 64
  }' | jq
```

## Configuration (runtime env vars)

The full list and their rationale lives in the comments at the top of
[`entrypoint.sh`](./entrypoint.sh). Short summary:

| Env var                    | Default                                   | Notes                                                                |
| -------------------------- | ----------------------------------------- | -------------------------------------------------------------------- |
| `PORT`                     | `8080`                                    | Cloud Run injects this. Server MUST bind to it.                      |
| `SERVED_MODEL_NAME`        | `Qwen/Qwen3-Coder-30B-A3B-Instruct`       | Name the agent addresses. Don't change without updating the agent.   |
| `QUANTIZATION`             | `awq_marlin`                              | Fast kernel path on L4 (SM89). Fall back to `awq` if Marlin regresses. |
| `MAX_MODEL_LEN`            | `32768`                                   | Per ADR-0013. Drop to `16384` if KV cache OOMs.                      |
| `MAX_NUM_SEQS`             | `4`                                       | MVP workload is single-client; larger values reserve VRAM we won't use. |
| `GPU_MEMORY_UTILIZATION`   | `0.90`                                    | Leave ~2.4 GiB for CUDA runtime + driver.                            |
| `ENFORCE_EAGER`            | `false`                                   | Disable CUDA graph capture if it OOMs at startup.                    |
| `HF_HUB_OFFLINE`           | `1` (baked in Dockerfile)                 | Safety net — weights are baked, so no HF calls at runtime.           |

### Secrets

The only secret the server could need is `HF_TOKEN` for a gated weights
repo, and that's only at **build time**. At runtime this container never
reaches out to HuggingFace (`HF_HUB_OFFLINE=1`), so no runtime secret is
required. If we ever need one, it MUST come from Secret Manager via a Cloud
Run env var, never from the image.

## Cloud Run sizing

- 1× NVIDIA L4 (24 GiB VRAM) — required by the model size.
- `min-instances: 0` (scale-to-zero, [ADR-0011][adr-0011]).
- `max-instances: 1` (MVP — no horizontal scaling yet).
- Cold-start budget: **20–60 s** (CUDA init + weight load + vLLM warmup).
  This is the accepted trade-off, documented in [ADR-0011][adr-0011].

## Testing

Two tiers, both under [`tests/`](./tests/):

### Offline tier — runs anywhere

```bash
cd services/model-server
uv sync --extra dev
uv run pytest tests/test_entrypoint.py tests/test_fetch_weights.py
```

These validate `entrypoint.sh`'s argv construction and `fetch_weights.py`'s
error paths. No GPU, no vLLM, no network.

### Live tier — requires a running vLLM server

```bash
MODEL_SERVER_URL=http://localhost:8080 \
  uv run pytest tests/test_openai_contract.py
```

Without `MODEL_SERVER_URL`, these tests are skipped. Set it to a local
docker instance (if you have a GPU host) or the deployed Cloud Run URL
(after devops-engineer pushes the image).

## Changing the model

1. Open a new ADR superseding [ADR-0013][adr-0013].
2. Update the `MODEL_HF_REPO` build-arg default in the
   [Dockerfile](./Dockerfile).
3. If the new model has a different chat template or tokenizer contract,
   that's an agent-side concern — loop in backend-engineer.

## Rollback

All configuration lives in the Dockerfile + entrypoint.sh. Reverting this
service to the previous (llama.cpp) runtime is `git revert` of the
`feat/vllm-model-server` merge commit, followed by `./scripts/build-and-push.sh
model-server` and `./scripts/deploy.sh apply`.

[adr-0001]: ../../docs/adr/0001-cloud-run-not-gke-for-poc.md
[adr-0010]: ../../docs/adr/0010-vllm-as-model-server-runtime.md
[adr-0011]: ../../docs/adr/0011-cloud-run-l4-gpu.md
[adr-0013]: ../../docs/adr/0013-qwen3-coder-30b-a3b-instruct-model.md
