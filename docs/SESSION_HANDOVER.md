# Session handover

> **Purpose**: the fastest path back into flow for the next contributor (human or agent). Update this at the end of every working session. Read it at the start of every session.

---

## Current state — 2026-04-21 (POC → MVP migration)

### What's landed (as feature branches, not merged to main)

Four PR candidates sit on local branches, reviewed end-to-end by qa-engineer + tech-lead, post-review integration breaks already fixed. **Nothing has been deployed.**

- **`docs/adr-mvp-decisions`** (1 commit) — the MVP decision cluster: [ADR-0010](adr/0010-vllm-as-model-server-runtime.md) vLLM supersedes llama.cpp; [ADR-0011](adr/0011-cloud-run-l4-gpu.md) Cloud Run NVIDIA L4 GPU, scale-to-zero retained, 20–60 s cold start explicitly accepted; [ADR-0012](adr/0012-reintroduce-deepagents.md) re-introduce DeepAgents (supersedes ADR-0009); [ADR-0013](adr/0013-qwen3-coder-30b-a3b-instruct-model.md) `Qwen/Qwen3-Coder-30B-A3B-Instruct` in AWQ int4 (supersedes ADR-0008). Status + index updates on 0002/0008/0009 and [DECISIONS.md](DECISIONS.md).

- **`feat/vllm-model-server`** (8 commits) — `services/model-server/` rewritten as a vLLM shim on a CUDA base (AWQ-Marlin quantization, baked model weights, argv-rewrite contract tests, `MAX_NUM_SEQS=4` for MVP single-client workload). `infra/terraform/` adds a `cloud_run_gpu` module (L4, `us-central1`) and a second Artifact Registry repo in that region. `scripts/build-and-push.sh` now defaults to Cloud Build for the CUDA image. Updated `smoke-test.sh`, `teardown.sh`, new `setup-billing-alerts.sh` (budget $300/mo, alerts 50/90/100%). Post-review fix: env var names aligned (`SERVED_MODEL_NAME` / `MAX_MODEL_LEN`, not `VLLM_*`) and the value pinned to the full HF id so the agent→server call doesn't 404.

- **`feat/reintroduce-deepagents-clean`** (2 commits) — `services/coder-agent/` migrated to `deepagents==0.5.3` + `langgraph>=1.1`. Plan→analyze→implement→refine as DeepAgents subagents (Shape A per ADR-0012). External FastAPI API unchanged. **35 pytest cases pass** (1 skipped live-model gate). Includes a new ADR-0001 compliance test that asserts `coder_agent.agent` never transitively imports `vllm` / `llama_cpp`. Model-name default now matches vLLM (`Qwen/Qwen3-Coder-30B-A3B-Instruct`).

- **`docs/session-handover-mvp-migration`** (this commit) — SESSION_HANDOVER update.

Two dead branches on disk from a parallel-agent working-tree race: `feat/cloud-run-gpu-l4` (contaminated) and `feat/reintroduce-deepagents` (empty). Safe to `git branch -d` both.

### What's in-flight / caveats

- **Nothing deployed, no images pushed.** GCP saw no changes this session. First `terraform apply` will want a real `model_server_image` URI (current placeholder in tfvars: `model-server:v0.2.0-sha-placeholder`).
- **GPU quota must be requested before apply**: GCP Console → IAM & Admin → Quotas → "Total Nvidia L4 GPU allocation, per project per region" → `us-central1` → at least 1. Default for new projects is 0.
- **`max_model_len=32768` is a proposal, not a measurement.** ml-engineer must validate on real L4 (ADR-0013). `entrypoint.sh` exposes `MAX_MODEL_LEN` so the operator can drop to 24576 / 16384 without rebuilding if vLLM OOMs on CUDA-graph capture.
- **Regional split.** coder-agent stays in `europe-west4`; model-server goes to `us-central1` (Cloud Run L4 not in europe-west4 as of 2026-04). ~100–130 ms cross-region RTT per agent→model call — documented in [RUNBOOK](RUNBOOK.md).
- **Cost envelope jumped.** Budget alert threshold raised from $20 → $300/mo. L4 on Cloud Run ~$0.90/hr warm; 8 active hrs/day ≈ $220/mo.

### Next actions (in priority order)

1. **Review + merge branches in order:**
   1. `docs/adr-mvp-decisions` (decisions, no risk)
   2. `feat/vllm-model-server` (container + GPU infra — coupled, must ship together)
   3. `feat/reintroduce-deepagents-clean` (depends on vLLM model-server being live)
   4. `docs/session-handover-mvp-migration` (this update)
2. `git branch -d feat/cloud-run-gpu-l4 feat/reintroduce-deepagents` once you're satisfied the clean branches captured the intent.
3. **Request L4 quota** in `us-central1`.
4. **Build + push images:** `./scripts/build-and-push.sh model-server` (Cloud Build default now) then `./scripts/build-and-push.sh coder-agent`. Update `terraform.tfvars` with the resulting digests/tags.
5. **Deploy:** `./scripts/deploy.sh plan` → review → `./scripts/deploy.sh apply`.
6. **Smoke test:** `./scripts/smoke-test.sh` — expect 20–60 s first-hit latency.
7. **Validate `max_model_len`** against real L4 VRAM; if vLLM OOMs, set `MAX_MODEL_LEN=24576` or `16384` via the service env, and note the measurement in ADR-0013.

### Deferred (not blocking MVP)

- **503-during-load contract test** on model-server `/health` (qa-engineer flagged; requires mocking vLLM startup phases).
- **Sub-agent Bash permissions.** Orchestrator, qa-engineer, and one doc-keeper invocation hit Bash auto-denial in background sub-agents this session — they could `Read/Grep/Glob/Write/Edit` but not run scripts, `git`, `pytest`, `terraform plan`, or `uv`. Static audits worked; test execution did not. Worth a follow-up on permission config so background agents can run verification.
- `_GoogleIdTokenAuth` auth ADR (carried over).
- Image-tag pinning convention (carried over).
- `pythonjsonlogger.jsonlogger` deprecation warning (carried over — trivial).

### Open questions for the next session

- Warmup ping or temporary `min_instances=1` for demos (trades idle-zero for predictable first response)?
- Does the cross-region split hold once real agent loops (10+ model calls each) are in play, or do we need to co-locate in us-central1?
- Is tool-use (file read/write, shell) the next feature on top of the DeepAgents graph, or do we stabilize single-turn-with-planning first?

### Known issues / gotchas

- **Sub-agent Bash permissions** — see Deferred above. Plan to tackle next.
- **Parallel code-writing agents need `isolation: "worktree"`**. This session's initial fan-out (ml + devops + backend concurrent, shared working tree) thrashed `.git/HEAD` and one agent's broad `git add` swept another's uncommitted work into its commit — ~30 min of surgical cleanup required. Memorialized as a feedback memory. Rule: any parallel Agent dispatch where ≥ 2 agents will write code gets `isolation: "worktree"`; read-only reviewers can share the main tree.
- **`/ready` 5 s probe timeout is now too tight** for vLLM's 60 s cold start. Bump or decouple from a full `/health` round-trip (carried over, now load-bearing).
- `openai` SDK retries twice on 500 s; expect three stacktraces in logs per failing request.

### Cost-to-date

- Zero incremental GCP cost this session. No deploys, no registry pushes.
- Project still sits at ~$0.10–$0.20/mo at idle. First apply will add a second ~10 GiB AR repo (~$1.50/mo) plus L4-hours once the service handles requests.

### Hand-off plan

Sub-agent team owns follow-up:

1. `devops-engineer` — runs the deploy after quota lands; bumps the `/ready` probe timeout; resolves the sub-agent Bash permission config.
2. `qa-engineer` — 503-during-load contract test; live-model integration test wired into CI behind an env gate.
3. `ml-engineer` — validates `max_model_len=32768` on real L4; revisits the AWQ repo choice (`cpatonn/Qwen3-Coder-30B-A3B-Instruct-AWQ-4bit`) when an official Qwen AWQ ships.
4. `doc-keeper` — updates ADR-0013 with the measured `max_model_len`; the two carried-over ADRs (history-squash, Google-ID-token auth).
5. `orchestrator` — coordinates when the deploy hits cross-cutting trouble.

---

## How to use this file

1. **Start of session**: read "Current state" top-to-bottom. Decide what to work on based on "Next actions".
2. **During session**: if you make a decision worth recording, write an ADR in [`docs/adr/`](adr/).
3. **End of session**: replace the dated block above with a fresh one. Move the previous block into the archive section below if it has history worth keeping. Keep only the last 2–3 in-line; archive older ones.

---

## Archive

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
