# Decision log

All non-trivial choices for this project are recorded as ADRs (Architectural Decision Records) under [adr/](adr/). This file is just the index — read the individual ADRs for rationale, alternatives considered, and consequences.

**Rule**: to change a decision, write a *new* ADR that supersedes the old one. Don't edit history.

## Index

| # | Status | Title |
|---|---|---|
| [0001](adr/0001-cloud-run-not-gke-for-poc.md) | Accepted | Cloud Run, not GKE+KServe, for Phase 1 |
| [0002](adr/0002-llama-cpp-for-poc-model-server.md) | Superseded by [#0010](adr/0010-vllm-as-model-server-runtime.md) | llama.cpp as the POC model server |
| [0003](adr/0003-deepagents-as-agent-framework.md) | Accepted — re-affirmed by [#0012](adr/0012-reintroduce-deepagents.md) | DeepAgents as the agent framework |
| [0004](adr/0004-europe-west4-region.md) | Accepted | Deploy to europe-west4 |
| [0005](adr/0005-uv-as-package-manager.md) | Accepted | uv for Python packaging |
| [0006](adr/0006-github-actions-for-ci.md) | Accepted | GitHub Actions for CI, not Cloud Build |
| [0007](adr/0007-no-database-for-poc.md) | Accepted | No database for the POC |
| [0008](adr/0008-qwen25-coder-15b-model.md) | Superseded by [#0013](adr/0013-qwen3-coder-30b-a3b-instruct-model.md) | Qwen2.5-Coder-1.5B-Instruct as POC model |
| [0009](adr/0009-strip-deepagents-for-poc-chat.md) | Superseded by [#0012](adr/0012-reintroduce-deepagents.md) | Strip DeepAgents for the POC chat path |
| [0010](adr/0010-vllm-as-model-server-runtime.md) | Accepted | vLLM as model server runtime |
| [0011](adr/0011-cloud-run-l4-gpu.md) | Accepted | Cloud Run with NVIDIA L4 GPU for MVP serving |
| [0012](adr/0012-reintroduce-deepagents.md) | Accepted | Re-introduce DeepAgents as agent framework |
| [0013](adr/0013-qwen3-coder-30b-a3b-instruct-model.md) | Accepted | Qwen3-Coder-30B-A3B-Instruct as MVP model |

## ADR lifecycle

Each ADR has a **status**:
- `Proposed` — open for discussion
- `Accepted` — in effect
- `Superseded by #NNNN` — overruled by a later ADR, keep the file for history
- `Deprecated` — no longer applies, but not replaced

## Template

See [adr/TEMPLATE.md](adr/TEMPLATE.md) to start a new one. Copy, number it next in sequence, fill in, link from this index.
