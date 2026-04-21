# Architecture

## Components

### model-server (Cloud Run)
- Runtime: **llama.cpp** (`ghcr.io/ggml-org/llama.cpp:server`).
- Model: **Qwen2.5-Coder-1.5B-Instruct**, quantized to **Q4_K_M** GGUF (~1 GB).
- Exposes an **OpenAI-compatible** API on `/v1/chat/completions` and `/v1/completions`.
- Sizing (POC): 2 vCPU, 4 GiB memory, `min_instances=0`, `max_instances=2`.
- Cold start: ~5–15 s to mmap the model.
- Auth: Cloud Run IAM — only the `coder-agent` service account can invoke.

### coder-agent (Cloud Run)
- Runtime: **Python 3.12** + **FastAPI** + **langchain-openai** (single-turn chat loop for Phase 1 — see [ADR 0009](adr/0009-strip-deepagents-for-poc-chat.md); DeepAgents is slated to return with tool use).
- Points at `model-server` URL via env var; uses `langchain-openai` client against the OpenAI-compatible endpoint.
- Exposes `/chat` (single-turn JSON `{request_id, output}`), `/health`, `/ready`.
- Sizing (POC): 1 vCPU, 1 GiB memory, `min_instances=0`, `max_instances=3`.
- Auth: inbound via ID-token; outbound (to private model-server) via Google-minted ID token attached by a custom `_GoogleIdTokenAuth` httpx auth class wired into the LangChain `ChatOpenAI` client.

### Supporting GCP resources
| Resource | Purpose |
|---|---|
| **Artifact Registry** (`europe-west4`) | Docker images for both services. |
| **Secret Manager** | Any future API keys / tokens. Empty at POC. |
| **Cloud Storage bucket** (`<project>-tfstate`) | Terraform remote state. |
| **Cloud Storage bucket** (`<project>-artifacts`) | Agent run artifacts, generated code, traces. |
| **Service accounts** | Per-service, least-privilege. `coder-agent-sa` can invoke `model-server`. |

## Request flow (chat — Phase 1, single-turn)

```
 Client ──ID-token──▶ coder-agent (/chat)
                        │
                        ▶ ChatAgent (single-turn)
                           └─ langchain-openai AsyncClient
                                + _GoogleIdTokenAuth (audience = model-server URL)
                                       │
                                       ▼
                                model-server /v1/chat/completions
                                       │
                                       ▼
                                 llama.cpp + Qwen (Q4 GGUF)
```

Phase 2 will reintroduce a graph (plan / analyze / implement / refine) once
we pair with a runtime that handles OpenAI tool-calling cleanly. See
[ADR 0009](adr/0009-strip-deepagents-for-poc-chat.md).

## Phase 2 migration (GKE + KServe)

The agent speaks OpenAI-compatible HTTP. To migrate:

1. Stand up a GKE Autopilot cluster + KServe.
2. Deploy an `InferenceService` running vLLM with the same model (or a larger one).
3. Switch `MODEL_SERVER_URL` env var on the coder-agent Cloud Run service to the KServe endpoint.
4. `langchain-kserve` is a drop-in alternative to `langchain-openai` if you want V2 protocol, but not required while vLLM is serving the OpenAI endpoint shape.

No agent code changes. No Terraform changes outside a new `gke/` module. See [docs/adr/0001-cloud-run-not-gke-for-poc.md](adr/0001-cloud-run-not-gke-for-poc.md) for the trigger conditions.

## Observability

- **Logs** → Cloud Logging (structured JSON via `python-json-logger`).
- **Metrics** → Cloud Run built-in (request count, latency, instance count). Budget alerts on the project.
- **Traces** (future) → OpenTelemetry exporter to Cloud Trace.

## Security posture (POC)

- Both services require authenticated invocation.
- `coder-agent-sa` has `run.invoker` on `model-server` only.
- No inbound internet on the model-server — only the coder-agent can reach it.
- Docker images run as non-root.
- Secrets in Secret Manager, mounted as env vars at boot.
- No outbound egress controls at POC — revisit if codebase compliance requires it.

## What's intentionally missing

- No database. POC holds no state between requests. When we need sessions/conversation history, revisit (ADR required).
- No Redis / queue. Requests are synchronous.
- No frontend. CLI / curl only for now.
- No auth service. GCP IAM does the heavy lifting via ID tokens.
- No custom domain, no Cloud Armor, no WAF. POC, internal.
