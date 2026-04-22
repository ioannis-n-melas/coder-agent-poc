# Architecture

## Components

### model-server (Cloud Run, GPU)
- Runtime: **vLLM** (see [ADR 0010](adr/0010-vllm-as-model-server-runtime.md)).
- Model: **Qwen3-Coder-30B-A3B-Instruct**, **AWQ int4** quantization (~16–18 GB weights). See [ADR 0013](adr/0013-qwen3-coder-30b-a3b-instruct-model.md). The AWQ tokenizer ships without a `chat_template`, so `scripts/fetch_weights.py` overlays the official template at image bake time.
- Exposes an **OpenAI-compatible** API on `/v1/chat/completions` and `/v1/completions`, with auto tool-choice + Hermes parser enabled (`--enable-auto-tool-choice --tool-call-parser hermes`).
- Sizing: **8 vCPU**, **32 GiB memory**, **NVIDIA L4 GPU** (no zonal redundancy — see [ADR 0011](adr/0011-cloud-run-l4-gpu.md) and [ADR 0014](adr/0014-consolidate-model-server-to-europe-west4.md)). `min_instances=0`, `max_instances=1`. See `infra/terraform/variables.tf` for current defaults.
- Cold start: ~20–60 s for vLLM warmup + AWQ weight load on L4 (`startup_cpu_boost=true`, `enforce_eager=true` to skip CUDA-graph capture).
- Auth: Cloud Run IAM — only the `coder-agent` service account can invoke.

### coder-agent (Cloud Run)
- Runtime: **Python 3.12** + **FastAPI** + **DeepAgents** over LangChain (`langchain-openai` `ChatOpenAI` for the model client). See [ADR 0012](adr/0012-reintroduce-deepagents.md).
- Drives a planner/refine graph against the OpenAI-compatible model endpoint. `MODEL_SERVER_URL` is the only env knob the agent uses to find the model.
- Exposes `/chat` (`{request_id, output}`), `/health`, `/ready`.
- Sizing: see `infra/terraform/variables.tf` (`coder_agent_cpu` / `coder_agent_memory`). `min_instances=0`.
- Auth: inbound via Cloud Run ID-token; outbound (to private model-server) via Google-minted ID token attached by a custom `_GoogleIdTokenAuth` httpx auth class wired into `ChatOpenAI`.

### billing-kill-switch (Cloud Function gen2 → Cloud Run)
- Subscribes to a Pub/Sub topic fed by a billing-account-scoped budget. When the project crosses the cap (£500 GBP), it disables billing on the project. See [ADR 0015](adr/0015-billing-hard-cap.md).
- `DRY_RUN=true` by default; flip to `false` once you're comfortable with the destructive path.

### Supporting GCP resources
| Resource | Purpose |
|---|---|
| **Artifact Registry** (`europe-west4`) | Docker images for both services. |
| **Secret Manager** | API keys / tokens (e.g. HF token used at image bake). |
| **Cloud Storage bucket** (`<project>-tfstate`) | Terraform remote state. |
| **Cloud Storage bucket** (`<project>-artifacts`) | Agent run artifacts, generated code, traces. |
| **Service accounts** | Per-service, least-privilege. `coder-agent-sa` can invoke `model-server`. |

## Request flow (chat)

```
 Client ──ID-token──▶ coder-agent (/chat)
                        │
                        ▶ DeepAgents graph (planner / refine)
                           └─ langchain-openai AsyncClient
                                + _GoogleIdTokenAuth (audience = model-server URL)
                                       │
                                       ▼
                                model-server /v1/chat/completions
                                       │
                                       ▼
                                vLLM + Qwen3-Coder-30B-A3B (AWQ int4) on L4
```

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
