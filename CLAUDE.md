# CLAUDE.md — Contributor rules for this repo

**This file is the contract.** Claude Code, sub-agents, and human contributors all follow it. If something here is wrong or outdated, **update it in the same PR** that invalidates it.

---

## 1. What this project is

A Kubernetes-native coder agent POC. Two services on Cloud Run today; a migration path to GKE + KServe tomorrow. Everything deploys from scripts/Terraform. See [README.md](README.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Design tenets** (do not violate without ADR):

1. **Agent ⇄ model contract is OpenAI-compatible HTTP.** Agent code never knows whether the backend is llama.cpp, vLLM, or KServe. Swapping runtimes = swap URL only.
2. **Scale to zero by default.** No component has a baseline cost when idle. Anything that can't scale to zero needs an ADR explaining why.
3. **All infra is code.** No click-ops in the GCP console for anything persistent. Every resource is in [infra/terraform/](infra/terraform/) or a `scripts/*.sh`. If you create something manually to debug, delete it and codify it.
4. **Every lifecycle op has a script.** Bootstrap, build, deploy, smoke-test, teardown. Idempotent. Re-runnable.
5. **Low cost first, optimize later.** POC lives on CPU. Don't add GPU / GKE / databases without a concrete trigger documented in an ADR.

---

## 2. Decision log is authoritative

Non-trivial choices (tech, architecture, model, region, framework) live in [docs/DECISIONS.md](docs/DECISIONS.md) as ADRs under [docs/adr/](docs/adr/). **If you change a decision, write a new ADR that supersedes the old one — don't mutate history.**

When in doubt about "why is X this way?" — read the ADRs first, not the code.

---

## 3. Working rules (hard requirements)

### 3.1 Documentation is not optional

- Changed public behavior? Update [README.md](README.md) and/or [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) in the same PR.
- Made a non-trivial decision? Write a new ADR in [docs/adr/](docs/adr/) and link it from [docs/DECISIONS.md](docs/DECISIONS.md).
- Added a new script? Document it in [docs/RUNBOOK.md](docs/RUNBOOK.md) under the appropriate lifecycle section.
- End of a working session? Update [docs/SESSION_HANDOVER.md](docs/SESSION_HANDOVER.md) — what changed, what's in-flight, what the next person (or future-you) needs to know.

### 3.2 Code discipline

- **Run the code** before declaring a task done. Not "I wrote it and it looks right" — actually invoke it. Type checks and tests verify correctness, not behavior.
- **Write tests** for new logic. Python tests live next to the service they test (`services/<svc>/tests/`). Use `pytest`. Aim for behavior tests, not coverage theater.
- **Never commit secrets.** Use [.env.example](.env.example) for templates. Real values go in Secret Manager. Anything matching a secret pattern gets blocked by pre-commit (when wired up).
- **Small commits, descriptive messages.** Conventional commits preferred (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`). One concern per commit.

### 3.3 Tooling

- Python: **uv** for deps and venvs. Don't use pip directly. `uv sync` / `uv run` / `uv add`.
- Python version: **3.12** (pinned in [.python-version](.python-version)).
- Infra: **Terraform ≥ 1.7**. GCS backend for state — never commit `.tfstate`.
- Container builds: multi-stage Dockerfiles. Non-root runtime user.
- Shell scripts: `set -euo pipefail` at the top. POSIX-first where possible, bash if needed.

### 3.4 GCP hygiene

- All service accounts are created in Terraform with minimum scopes.
- All secrets go to Secret Manager, never to env vars in `terraform.tfvars`.
- Cloud Run services require authentication by default (`--no-allow-unauthenticated`). Opening a service to the world needs an ADR.
- Billing alerts must exist before anything non-free is deployed. Script: `scripts/setup-billing-alerts.sh`.

---

## 4. Agent team (sub-agents)

Sub-agents live in [.claude/agents/](.claude/agents/). Each has a scoped role — invoke the right one for the task.

| Agent | Use when |
|---|---|
| `orchestrator` | Multi-step project work spanning multiple agents. Plans, dispatches, verifies. |
| `tech-lead` | Architecture review, design tradeoffs, PR code review, cross-cutting decisions. |
| `backend-engineer` | Python / FastAPI / API design / data modeling. |
| `devops-engineer` | Terraform, Cloud Run, GCP IAM, CI/CD, networking, observability. |
| `ml-engineer` | Model choice, serving runtime (llama.cpp / vLLM / KServe), prompt & context engineering. |
| `qa-engineer` | Test design, smoke tests, contract tests against the OpenAI-compatible endpoint. |
| `doc-keeper` | ADRs, SESSION_HANDOVER updates, RUNBOOK maintenance, README freshness. |

The main thread defers to these specialists for their domain — don't re-solve what a specialist can solve. Use the `Task`/`Agent` tool pattern.

---

## 5. Standard commands

```bash
# Setup
./scripts/check-prereqs.sh             # verify gcloud, terraform, uv, docker installed
./scripts/bootstrap-gcp.sh             # one-time: state bucket, enable APIs, service accounts

# Daily development (local)
./scripts/dev.sh up                    # run both services locally via docker-compose
./scripts/dev.sh test                  # run all tests
./scripts/dev.sh lint                  # ruff + mypy
./scripts/dev.sh down                  # stop local services

# Deployment
./scripts/build-and-push.sh [service]  # build + push one or both service images
./scripts/deploy.sh [plan|apply]       # terraform plan/apply
./scripts/smoke-test.sh                # hit deployed endpoints, verify chat completes
./scripts/teardown.sh                  # tear down Cloud Run services (keeps AR, state, project)
```

---

## 6. When you're about to...

- **...make a model choice** → update [docs/adr/0002](docs/adr/0002-llama-cpp-for-poc-model-server.md) or write a superseding ADR. Check [ml-engineer](.claude/agents/ml-engineer.md) first.
- **...add a GCP resource** → write Terraform for it. No exceptions for "just one thing."
- **...install a Python package** → `uv add <pkg>` (or `uv add --dev <pkg>`). Commit `uv.lock`.
- **...start a new session** → read [docs/SESSION_HANDOVER.md](docs/SESSION_HANDOVER.md) first. It's the fastest path back into flow.
- **...end a session** → update [docs/SESSION_HANDOVER.md](docs/SESSION_HANDOVER.md). Summarize state, in-flight work, next actions.

---

## 7. What NOT to do

- ❌ Don't add Cloud SQL / Redis / any stateful service without an ADR (POC doesn't need one).
- ❌ Don't add a GKE cluster "to match the article" — that's Phase 2, triggered by concrete need.
- ❌ Don't put production code in the model server — it's a thin shim over llama.cpp. Agent logic belongs in `coder-agent`.
- ❌ Don't skip tests because "it's a POC." POC ≠ unverified.
- ❌ Don't widen Cloud Run IAM to `allUsers` without an ADR.
- ❌ Don't touch main directly — PRs only, even for solo work. The log matters.

---

*Last updated: 2026-04-19. Update this file as the project evolves.*
