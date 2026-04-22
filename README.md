# coder-agent-poc

A Kubernetes-native coder agent — **Phase 1** runs on Google Cloud Run with a self-hosted LLM, **Phase 2** migrates to GKE + KServe without touching the agent code.

Inspired by *[A Kubernetes-Native Coder Agent: DeepAgent + KServe + Self-Hosted LLMs](https://medium.com/@mrschneider/a-kubernetes-native-coder-agent-deepagent-kserve-self-hosted-llms-59e829e3be7d)* (Marton Schneider, Mar 2026).

**Status:** MVP green end-to-end. See [docs/SESSION_HANDOVER.md](docs/SESSION_HANDOVER.md) for the latest state.

## What it is

A coder agent talking to a self-hosted model through an OpenAI-compatible HTTP endpoint. Three Cloud Run services:

- **`model-server`** — vLLM serving **Qwen3-Coder-30B-A3B-Instruct** (AWQ int4 quantization, ~16 GB) on **NVIDIA L4 GPU**. See [ADR 0010](docs/adr/0010-vllm-as-model-server-runtime.md) (vLLM), [ADR 0011](docs/adr/0011-cloud-run-l4-gpu.md) (L4 GPU), and [ADR 0013](docs/adr/0013-qwen3-coder-30b-a3b-instruct-model.md) (model).
- **`coder-agent`** — Python 3.12 / FastAPI driving a **DeepAgents** planner/refine graph against the model endpoint. See [ADR 0012](docs/adr/0012-reintroduce-deepagents.md).
- **`billing-kill-switch`** — Cloud Function (gen2) wired to a billing-account budget topic; disables billing if the project crosses the cap. See [ADR 0015](docs/adr/0015-billing-hard-cap.md).

All three deploy with `min_instances=0` (true scale-to-zero).

## Quick start

```bash
# 1. Prerequisites
./scripts/check-prereqs.sh

# 2. One-time GCP bootstrap (creates state bucket, service accounts)
./scripts/bootstrap-gcp.sh

# 3. Build & push images to Artifact Registry
./scripts/build-and-push.sh

# 4. Deploy via Terraform
./scripts/deploy.sh

# 5. Smoke test
./scripts/smoke-test.sh
```

## Architecture at a glance

```
  ┌──────────────┐      OpenAI-compatible HTTP      ┌──────────────┐
  │ coder-agent  │ ───────────────────────────────▶ │ model-server │
  │ Cloud Run    │      (ID-token Bearer)           │ Cloud Run    │
  │ FastAPI +    │                                  │ vLLM + L4    │
  │ DeepAgents   │                                  │ Qwen3-Coder  │
  └──────────────┘                                  └──────────────┘
         │                                                  │
         └──── GCP Secret Manager ──── Cloud Storage ───────┘
                                       (model cache, artifacts)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details and [docs/adr/](docs/adr/) for decision records.

## Repository structure

```
.
├── .claude/              # Claude Code sub-agents, hooks, settings
│   └── agents/           #   orchestrator, tech-lead, backend, devops, ml, qa, doc-keeper
├── .github/workflows/    # CI (lint, test, build)
├── CLAUDE.md             # Rules & conventions Claude + contributors follow
├── docs/
│   ├── ARCHITECTURE.md   # System design
│   ├── DECISIONS.md      # ADR index
│   ├── RUNBOOK.md        # How to operate/debug
│   ├── SESSION_HANDOVER.md  # Cross-session state — updated every session
│   └── adr/              # Architectural decision records
├── infra/terraform/      # All GCP infra as code
├── scripts/              # Idempotent bash scripts for every lifecycle op
├── services/
│   ├── model-server/     # vLLM + Qwen3-Coder-30B AWQ (L4 GPU)
│   └── coder-agent/      # FastAPI + DeepAgents
└── tools/                # Dev utilities
```

## Cost profile (POC)

Scale-to-zero across all services. Idle cost ≈ **£0.10/mo** (Artifact Registry + Terraform state bucket). Active cost dominated by L4 GPU at ~£0.72/hr; typical POC use 2–4 hrs/day → **£1.50–3.00/day**. A billing-account budget is hard-capped at £500 GBP via the `billing-kill-switch` ([ADR 0015](docs/adr/0015-billing-hard-cap.md)).

See [docs/RUNBOOK.md](docs/RUNBOOK.md#cost) for monitoring details.

## License

POC code, public for reference. No license file is committed, so default copyright applies — feel free to read and fork the ideas, but reuse of the code itself is reserved. If you need an explicit license, open an issue.
