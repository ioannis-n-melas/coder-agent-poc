# Decision log

All non-trivial choices for this project are recorded as ADRs (Architectural Decision Records) under [adr/](adr/). This file is just the index — read the individual ADRs for rationale, alternatives considered, and consequences.

**Rule**: to change a decision, write a *new* ADR that supersedes the old one. Don't edit history.

## Index

| # | Status | Title |
|---|---|---|
| [0001](adr/0001-cloud-run-not-gke-for-poc.md) | Accepted | Cloud Run, not GKE+KServe, for Phase 1 |
| [0002](adr/0002-llama-cpp-for-poc-model-server.md) | Accepted | llama.cpp as the POC model server |
| [0003](adr/0003-deepagents-as-agent-framework.md) | Partially superseded by [#0009](adr/0009-strip-deepagents-for-poc-chat.md) | DeepAgents as the agent framework |
| [0004](adr/0004-europe-west4-region.md) | Accepted | Deploy to europe-west4 |
| [0005](adr/0005-uv-as-package-manager.md) | Accepted | uv for Python packaging |
| [0006](adr/0006-github-actions-for-ci.md) | Accepted | GitHub Actions for CI, not Cloud Build |
| [0007](adr/0007-no-database-for-poc.md) | Accepted | No database for the POC |
| [0008](adr/0008-qwen25-coder-15b-model.md) | Accepted | Qwen2.5-Coder-1.5B-Instruct as POC model |
| [0009](adr/0009-strip-deepagents-for-poc-chat.md) | Accepted | Strip DeepAgents for the POC chat path |

## ADR lifecycle

Each ADR has a **status**:
- `Proposed` — open for discussion
- `Accepted` — in effect
- `Superseded by #NNNN` — overruled by a later ADR, keep the file for history
- `Deprecated` — no longer applies, but not replaced

## Template

See [adr/TEMPLATE.md](adr/TEMPLATE.md) to start a new one. Copy, number it next in sequence, fill in, link from this index.
