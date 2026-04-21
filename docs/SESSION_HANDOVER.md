# Session handover

> **Purpose**: the fastest path back into flow for the next contributor (human or agent). Update this at the end of every working session. Read it at the start of every session.

---

## Current state — 2026-04-21 (post-merge: MVP migration complete)

### What's landed

PRs #6–#10 merged into `main` (`c679b89`). The MVP migration cluster is fully in `main`. **Nothing deployed to GCP yet.**

| PR | Branch | What it brought in |
|---|---|---|
| #6 | `docs/adr-mvp-decisions` | [ADR-0010](adr/0010-vllm-as-model-server-runtime.md) vLLM supersedes llama.cpp; [ADR-0011](adr/0011-cloud-run-l4-gpu.md) Cloud Run L4 GPU; [ADR-0012](adr/0012-reintroduce-deepagents.md) DeepAgents re-introduced; [ADR-0013](adr/0013-qwen3-coder-30b-a3b-instruct-model.md) Qwen3-Coder-30B AWQ int4. Status updates on ADR-0002/0008/0009 and [DECISIONS.md](DECISIONS.md). |
| #7 | `chore/subagent-bash-permissions` | Orchestrator, qa-engineer, and doc-keeper background sub-agents can now run `git -C`, `git worktree`, `bash -n`, `shellcheck`. Resolves the "Sub-agent Bash permissions" deferred item from the prior block. |
| #8 | `feat/vllm-model-server` | `services/model-server/` rewritten as a vLLM shim on a CUDA base (AWQ-Marlin, baked weights, `MAX_NUM_SEQS=4`). `infra/terraform/` adds `cloud_run_gpu` module (L4, `us-central1`) + second AR repo. `scripts/build-and-push.sh` defaults to Cloud Build for CUDA image. Updated `smoke-test.sh`, `teardown.sh`, new `setup-billing-alerts.sh` ($300/mo budget). Env vars aligned (`SERVED_MODEL_NAME` / `MAX_MODEL_LEN`). |
| #9 | `feat/reintroduce-deepagents-clean` | `services/coder-agent/` migrated to `deepagents==0.5.3` + `langgraph>=1.1`. Plan→analyze→implement→refine subagent graph (Shape A per ADR-0012). External FastAPI API unchanged. 35 pytest cases pass (1 skipped live-model gate). ADR-0001 compliance test added. |
| #10 | `docs/session-handover-mvp-migration` | SESSION_HANDOVER update written pre-merge; content was accurate at time of writing, became stale on merge — replaced by this block. |

Dead branches `feat/cloud-run-gpu-l4` and `feat/reintroduce-deepagents` no longer exist locally or on origin. `terraform.tfvars` exists locally (not committed).

### What's in-flight / caveats

- **Nothing deployed, no images pushed.** `terraform.tfvars` still holds a placeholder model-server image URI. First `terraform apply` requires a real digest.
- **L4 GPU quota not yet confirmed.** GCP Console → IAM & Admin → Quotas → "Total Nvidia L4 GPU allocation, per project per region" → `us-central1` → at least 1. Default for new projects is 0.
- **`max_model_len=32768` is a proposal, not a measurement.** Must validate on real L4 (ADR-0013). `entrypoint.sh` exposes `MAX_MODEL_LEN` so the operator can drop to 24576 / 16384 without rebuilding.
- **Regional split.** coder-agent stays in `europe-west4`; model-server in `us-central1` (Cloud Run L4 not available in europe-west4 as of 2026-04). ~100–130 ms cross-region RTT per agent→model call — documented in [RUNBOOK](RUNBOOK.md).
- **Cost envelope.** Budget alert threshold is $300/mo. L4 on Cloud Run ~$0.90/hr warm; 8 active hrs/day ≈ $220/mo.
- **`/ready` 5 s probe timeout too tight for vLLM's 60 s cold start.** Load-bearing — must be bumped before first deploy.

### Next actions (in priority order)

1. **Confirm L4 quota** in `us-central1` is approved (GCP Console or `gcloud`).
2. **Build + push images:** `./scripts/build-and-push.sh model-server` (Cloud Build) then `./scripts/build-and-push.sh coder-agent`. Update `terraform.tfvars` with resulting digests/tags.
3. **Bump `/ready` probe timeout** on model-server Cloud Run service before applying (carried from caveats above).
4. **Deploy:** `./scripts/deploy.sh plan` → review → `./scripts/deploy.sh apply`.
5. **Smoke test:** `./scripts/smoke-test.sh` — expect 20–60 s first-hit latency.
6. **Validate `max_model_len`** against real L4 VRAM; if vLLM OOMs, set `MAX_MODEL_LEN=24576` or `16384` via service env and note measurement in ADR-0013.

### Deferred (not blocking MVP)

- **503-during-load contract test** on model-server `/health` (qa-engineer flagged; requires mocking vLLM startup phases).
- `_GoogleIdTokenAuth` auth ADR (carried over).
- Image-tag pinning convention (carried over).
- `pythonjsonlogger.jsonlogger` deprecation warning (carried over — trivial).

### Open questions for the next session

- Warmup ping or temporary `min_instances=1` for demos (trades idle-zero for predictable first response)?
- Does the cross-region split hold once real agent loops (10+ model calls each) are in play, or do we need to co-locate in `us-central1`?
- Is tool-use (file read/write, shell) the next feature on top of the DeepAgents graph, or do we stabilize single-turn-with-planning first?

### Cost-to-date

- Zero incremental GCP cost. No deploys, no registry pushes.
- Project at ~$0.10–$0.20/mo idle. First apply adds a second ~10 GiB AR repo (~$1.50/mo) plus L4-hours once the service handles requests.

### Hand-off plan

1. `devops-engineer` — confirm quota, run the deploy, bump `/ready` probe timeout.
2. `qa-engineer` — 503-during-load contract test; live-model integration test wired into CI behind an env gate.
3. `ml-engineer` — validate `max_model_len=32768` on real L4; revisit AWQ repo choice (`cpatonn/Qwen3-Coder-30B-A3B-Instruct-AWQ-4bit`) when an official Qwen AWQ ships.
4. `doc-keeper` — update ADR-0013 with measured `max_model_len`; write carried-over ADRs (`_GoogleIdTokenAuth`, image-tag pinning).
5. `orchestrator` — coordinates when the deploy hits cross-cutting trouble.

---

## How to use this file

1. **Start of session**: read "Current state" top-to-bottom. Decide what to work on based on "Next actions".
2. **During session**: if you make a decision worth recording, write an ADR in [`docs/adr/`](adr/).
3. **End of session**: replace the dated block above with a fresh one. Move the previous block into the archive section below if it has history worth keeping. Keep only the last 2–3 in-line; archive older ones.

---

## Archive

### 2026-04-21 — POC → MVP migration (pre-merge state)

Four PR candidates sat on local branches, reviewed end-to-end by qa-engineer + tech-lead. **Nothing had been deployed.** Branches: `docs/adr-mvp-decisions` (MVP decision cluster: ADR-0010–0013), `feat/vllm-model-server` (8 commits, vLLM shim + GPU infra), `feat/reintroduce-deepagents-clean` (35 pytest cases pass), `docs/session-handover-mvp-migration`. Two dead branches from a parallel-agent working-tree race — `feat/cloud-run-gpu-l4` and `feat/reintroduce-deepagents` — were present but not needed. The worktree race (ml + devops + backend concurrent, shared working tree) required ~30 min of surgical cleanup; memorialized in feedback memory: any parallel Agent dispatch where ≥ 2 agents write code must use `isolation: "worktree"`. Sub-agent Bash permissions deferred as a follow-up item (resolved in PR #7).

### 2026-04-21 — pre-public-release hygiene pass

- Repo audited for credential leakage (working tree + full history) — clean on API keys, tokens, private keys, service-account JSON, tfstate. Billing account ID was baked into 4 pre-existing commits, resolved via a full orphan-squash (`main` became a single `chore: initial commit` `9dd0308`). Branch protection on `main` restored after the one-time force-push.
- Hardcoded owner email as Cloud Run invoker → `coder_agent_invoker_members` list variable (no default, forces explicit set). Billing-account IDs in example files + docs → placeholders pointing at `.env` / `terraform.tfvars`.
- Local backup tags `backup/pre-squash-main` / `backup/pre-squash-chore` kept pre-wipe. PR #4 closed as superseded.
- Accepted residual risk: GitHub preserves `refs/pull/{1..4}/head` on origin pointing at pre-squash commits — only fetchable by knowing the PR number; not a credential, not worth the churn of a full repo re-create to purge.

### 2026-04-20 — end-to-end POC working

- **`/chat` unblocked.** Deployed `coder-agent` `/chat` returns 200 with non-empty output; verified via `./scripts/smoke-test.sh` against live Cloud Run.
- **DeepAgents stripped from the chat path.** Replaced `deepagents.create_deep_agent` with a plain `ChatOpenAI` loop in `services/coder-agent/src/coder_agent/agent.py`. See [ADR 0009](adr/0009-strip-deepagents-for-poc-chat.md) for rationale and the trigger to bring it back.
- **`_GoogleIdTokenAuth` preserved.** Private-to-private Cloud Run auth path unchanged — that was always the load-bearing piece, not the agent framework.
- **Both services redeployed.** `coder-agent` new revision; `model-server` image digest unchanged. Both still private, scale-to-zero.
- **22/22 unit tests pass.** `uv.lock` regenerated — 9 transitive deps dropped (deepagents, langgraph, anthropic, langchain-anthropic, google-genai, langchain-google-genai, docstring-parser, filetype, bracex, wcmatch).

### 2026-04-20 — first deployment

- **Both services deployed on Cloud Run.** `coder-agent` → `https://coder-agent-5eiztln6kq-ez.a.run.app`, `model-server` → `https://model-server-5eiztln6kq-ez.a.run.app`. Both private, scale to zero, images pinned by digest in `terraform.tfvars`. Terraform state at `gs://coder-agent-poc-2026-tfstate/terraform/state`. Budget module removed (using billing-account-wide alerts).
- **`/health` and `/ready` both pass end-to-end.** `/ready` confirmed `model_server_reachable: true` — Google ID token auth path works.
- **`/chat` returned 502 due to a DeepAgents ⇄ llama.cpp tool-calling incompatibility.** With `--jinja` enabled on llama-server, the Hermes-2-Pro template rejected DeepAgents' structured `content: null` assistant turns (`Expected 'content' to be a string or an array`).
- **Key changes** this session: `_GoogleIdTokenAuth` class for per-request Google ID-token minting; `REQUEST_TIMEOUT_SECONDS=300` env on coder-agent; `--jinja` on llama-server; smoke-test script fixed for user-account vs SA identity tokens; curl `--max-time` raised to 300 s. 18/18 unit tests passed at that point.
- **Unblock path** identified as four options. Resolved in the 2026-04-20 (end-to-end) block above via Option (a) — strip DeepAgents, plain chat loop. See [ADR 0009](adr/0009-strip-deepagents-for-poc-chat.md).

### 2026-04-19 — initial scaffold

- Private GitHub repo `ioannis-n-melas/coder-agent-poc` created.
- GCP project `coder-agent-poc-2026` created in `europe-west4`. Billing linked (ID tracked in `.env` / `terraform.tfvars`, not in-tree). APIs enabled.
- Full scaffold committed: `CLAUDE.md`, 8 ADRs, Terraform modules (artifact_registry, iam, storage, cloud_run, secret_manager, budget), `model-server` (llama.cpp + Qwen2.5-Coder-1.5B Q4), `coder-agent` (FastAPI + DeepAgents + langchain-openai), 7 sub-agents in `.claude/agents/`, GitHub Actions CI, `docker-compose.yml`, lifecycle scripts.
- 14/14 unit tests pass. Ruff lint + format clean. uv.lock generated.
- No GCP resources deployed yet beyond project + APIs. No images pushed.
