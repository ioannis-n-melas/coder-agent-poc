# coder-agent-poc

A Kubernetes-native coder agent — **Phase 1** runs on Google Cloud Run with a small self-hosted LLM, **Phase 2** migrates to GKE + KServe without touching the agent code.

Inspired by *[A Kubernetes-Native Coder Agent: DeepAgent + KServe + Self-Hosted LLMs](https://medium.com/@mrschneider/a-kubernetes-native-coder-agent-deepagent-kserve-self-hosted-llms-59e829e3be7d)* (Marton Schneider, Mar 2026).

## What it is

A coder agent talking to a self-hosted model through an OpenAI-compatible HTTP endpoint. Two services:

- **`model-server`** — llama.cpp serving Qwen2.5-Coder-1.5B-Instruct (Q4_K_M GGUF, ~1 GB). CPU-only for POC.
- **`coder-agent`** — Python / FastAPI + `langchain-openai`. Phase 1 runs a single-turn chat loop; Phase 2 reintroduces the planner/tools graph (see [ADR 0009](docs/adr/0009-strip-deepagents-for-poc-chat.md)).

Both deploy to Cloud Run with `min-instances=0` (true scale-to-zero).

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
  │ Cloud Run    │      (ID-token Bearer)            │ Cloud Run    │
  │ FastAPI +    │                                   │ llama.cpp    │
  │ ChatOpenAI   │                                   │              │
  └──────────────┘                                   └──────────────┘
         │                                                   │
         └──── GCP Secret Manager ──── Cloud Storage ────────┘
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
│   ├── model-server/     # llama.cpp container
│   └── coder-agent/      # FastAPI + langchain-openai (single-turn chat)
└── tools/                # Dev utilities
```

## Cost profile (POC)

Scale-to-zero + CPU-only. Idle cost ≈ **$0**. Active cost dominated by Cloud Run vCPU-seconds and Artifact Registry storage (<$1/mo for a ~1.5 GB image).

See [docs/RUNBOOK.md](docs/RUNBOOK.md#cost) for live monitoring.

## License

Private / proprietary (internal POC).
