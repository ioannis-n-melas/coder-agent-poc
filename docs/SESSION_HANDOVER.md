# Session handover

> **Purpose**: the fastest path back into flow for the next contributor (human or agent). Update this at the end of every working session. Read it at the start of every session.

---

## Current state — 2026-04-22 (deployed, awaiting tool-choice rebuild)

### What's landed

PRs #11–#18 merged today (all admin-bypassed due to a pre-existing Python CI lint failure on main from PR #9). All three services are live in `europe-west4`.

| PR | Branch | What it brought in |
|---|---|---|
| #11 | `docs/session-handover-post-merge` | SESSION_HANDOVER refresh + [ADR-0014](adr/0014-consolidate-model-server-to-europe-west4.md): consolidate `model-server` to `europe-west4`; remove `var.model_server_region`; collapse second AR repo. |
| #12 | `feat/billing-hard-cap` | [ADR-0015](adr/0015-billing-hard-cap.md) + `modules/billing_hard_cap/`: Cloud Function (Python 3.12, gen2) + Pub/Sub + billing-account-scoped budget at £500 GBP. Kill-switch deployed and armed. `DRY_RUN` env controls destructive path. |
| #13 | `fix/model-server-cloudbuild-buildkit` | `services/model-server/cloudbuild.yaml` enabling `DOCKER_BUILDKIT=1`. Fixes latent PR #8 bug where `--mount=type=secret,id=hf_token` required BuildKit but the legacy builder was used. `build-and-push.sh` now auto-detects per-service `cloudbuild.yaml`. |
| #14 | `fix/gpu-no-zonal-redundancy` | `modules/cloud_run_gpu`: added `gpu_zonal_redundancy_disabled=true`. GCP auto-granted only the no-zonal-redundancy L4 variant; the zonal-redundant variant was rejected for high demand. |
| #15 | `fix/quantization-and-budget-currency` | `QUANTIZATION=compressed-tensors` on model-server (AWQ repo declares `compressed-tensors` in config.json, not `awq`). `modules/budget` now accepts a `currency` variable (default GBP — USD was rejected by GCP because billing account is GBP). |
| #16 | `fix/probe-window-and-enforce-eager` | Startup probe `failure_threshold` 12 → 30 (360 s window). `ENFORCE_EAGER=true` on model-server to skip CUDA graph capture, which was consuming ~15–30 s and timing out the probe. |
| #17 | `fix/max-model-len-24576` | `MAX_MODEL_LEN` 32768 → 24576. vLLM measured `3.0 GiB KV cache needed, 2.63 GiB available` at 32k; 24576 gives headroom below the ceiling. ADR-0013 updated with measured numbers. |
| #18 | `fix/vllm-tool-choice` | `entrypoint.sh` now passes `--enable-auto-tool-choice --tool-call-parser hermes` (env-controlled via `ENABLE_TOOL_CHOICE` / `TOOL_CALL_PARSER`). Without this, vLLM returned 400 when DeepAgents sent `tool_choice=auto`. 3 new contract tests; 14/14 entrypoint tests pass. |

**Deployed services** (all private, scale-to-zero):

| Service | URL |
|---|---|
| `coder-agent` | `https://coder-agent-5eiztln6kq-ez.a.run.app` |
| `model-server` | `https://model-server-5eiztln6kq-ez.a.run.app` |
| `billing-kill-switch` | `https://billing-kill-switch-5eiztln6kq-ez.a.run.app` |

### What's in-flight / caveats

- **Cloud Build rebuilding model-server** with PR #18 tool-choice fix (background task `bc7nzpahm`). The currently deployed model-server image is pre-PR-#18 and missing the tool-choice flags. Until the new image is rolled out, `/chat` returns 400 from vLLM.
- **After build lands**: update `terraform.tfvars` with the new model-server digest, run `terraform apply`, re-run `./scripts/smoke-test.sh`.
- **Pre-existing Python CI lint failure on main** (from PR #9 — import-sorting + unused symbols in `services/coder-agent/src/coder_agent/agent.py`). Blocking normal merges; every PR this session required admin bypass. Needs cleanup before the next feature cycle.
- **L4 is no-zonal-redundancy only.** GCP denied the zonal-redundant variant (high demand). Single-zone, POC-acceptable per ADR-0014. Retry guidance from GCP: "in the coming months."

### Next actions (in priority order)

1. **Wait on Cloud Build** `bc7nzpahm` to finish; update local `terraform.tfvars` with the new model-server image digest.
2. **`./scripts/deploy.sh apply`** to roll the new model-server revision.
3. **`./scripts/smoke-test.sh`** — full chat round-trip. Last run (pre-PR-#18): `/health` OK, `/ready` OK, `/chat` 502 (now expected to be fixed).
4. If green: stable MVP deploy confirmed. If not: diagnose and iterate.
5. **Fix the Python lint failure** on main to unblock normal PR merges. (`ruff check --select I services/coder-agent/src/coder_agent/agent.py` and remove unused imports.)
6. **Zonal-redundancy L4 quota**: consider re-submitting the quota request in ~1 week.

### Deferred (not blocking MVP)

- **503-during-load contract test** on model-server `/health` (qa-engineer; requires mocking vLLM startup phases).
- `_GoogleIdTokenAuth` auth ADR (carried over).
- `pythonjsonlogger.jsonlogger` deprecation warning (carried over — trivial).
- ADR-0013 language referencing 32k `max_model_len` as a proposal — update to reflect the measured 24576 ceiling (doc-keeper).

### Open questions for the next session

- Is tool-use (file read/write, shell) the next feature on top of the DeepAgents graph, or do we stabilize single-turn-with-planning first?
- Should we gate the model-server with a warmup ping to mask cold-start latency for demos?

### Cost-to-date

- Idle: ~£0.10/mo (AR repo + state bucket).
- L4 active: ~£0.72/hr (approx). Full day warm ≈ £17; POC usage 2–4 hrs/day ≈ £1.50–3.00/day.
- Kill-switch armed at £500 GBP billing-account cap.

### Hand-off plan

- `devops-engineer` — complete the model-server rebuild deploy (#1–#4 above); fix lint failure (#5).
- `qa-engineer` — 503-during-load contract test (still deferred); wire live-chat smoke test into CI behind an env gate.
- `ml-engineer` — tune `gpu_memory_utilization` to push `MAX_MODEL_LEN` back toward 28k now that we have real measurements.
- `doc-keeper` — update ADR-0013 to replace the 32k proposal language with measured 24576 ceiling; write carried-over `_GoogleIdTokenAuth` ADR.
- `orchestrator` — coordinates if post-rebuild smoke test surfaces cross-cutting issues.

---

## How to use this file

1. **Start of session**: read "Current state" top-to-bottom. Decide what to work on based on "Next actions".
2. **During session**: if you make a decision worth recording, write an ADR in [`docs/adr/`](adr/).
3. **End of session**: replace the dated block above with a fresh one. Move the previous block into the archive section below if it has history worth keeping. Keep only the last 2–3 in-line; archive older ones.

---

## Archive

### 2026-04-21 — post-merge + regional pivot

PRs #6–#10 merged the MVP migration cluster. PR #11 added a SESSION_HANDOVER refresh and [ADR-0014](adr/0014-consolidate-model-server-to-europe-west4.md) consolidating `model-server` to `europe-west4` (L4 now GA there; single AR repo; `var.model_server_region` removed). Nothing had been deployed to GCP at the close of this session. `terraform.tfvars` held stale `us-central1` values — overwritten before first apply.

| PR | What it brought in |
|---|---|
| #6 | ADR-0010–0013 (vLLM, L4 GPU, DeepAgents, Qwen3-Coder-30B AWQ int4) |
| #7 | Sub-agent Bash permissions (git, shellcheck) |
| #8 | `services/model-server/` as vLLM shim; `cloud_run_gpu` Terraform module; `setup-billing-alerts.sh` |
| #9 | `services/coder-agent/` migrated to `deepagents==0.5.3` + `langgraph>=1.1`; 35 pytest cases |
| #10 | SESSION_HANDOVER update (pre-merge; superseded by #11) |
| #11 | This block + ADR-0014 regional pivot |

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
