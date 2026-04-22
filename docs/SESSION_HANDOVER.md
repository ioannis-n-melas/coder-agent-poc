# Session handover

> **Purpose**: the fastest path back into flow for the next contributor (human or agent). Update this at the end of every working session. Read it at the start of every session.

---

## Current state — 2026-04-22 (end of session: deployed + chat_template blocker)

### What's landed since the prior block

- **PR #19** (SESSION_HANDOVER refresh — merged on `main` at `5e62a22`): the prior block captured the mid-session state.
- **Cloud Build `ed6cfba3` finished** (23m01s). New model-server image pushed to AR:
  `sha256:5379d924e91a1cf3258f82ce29067511826713aa0fe986a9eca8f69f425bc0e7`. Local `terraform.tfvars` pinned to this digest.
- **`terraform apply` completed** (17m39s). First-time pull of the new ~17 GiB image — layer cache cold because digest changed. `model-server-00007-hrs` now serves 100% of traffic with the tool-choice fix active.

**Deployed services** (all private, scale-to-zero):

| Service | URL |
|---|---|
| `coder-agent` | `https://coder-agent-5eiztln6kq-ez.a.run.app` |
| `model-server` | `https://model-server-5eiztln6kq-ez.a.run.app` |
| `billing-kill-switch` | `https://billing-kill-switch-5eiztln6kq-ez.a.run.app` |

### Smoke test result (`./scripts/smoke-test.sh`)

| Check | Result |
|---|---|
| model-server `/health` | OK |
| coder-agent `/health` | OK |
| coder-agent `/ready` (`model_server_reachable: true`) | OK |
| coder-agent `/chat` | **502** |

### Blocker — next-session priority 1

**Chat template missing from AWQ tokenizer.**

vLLM now accepts `tool_choice=auto` (PR #18 fix verified). A new error surfaced from the tokenizer on the first real `/chat` call:

> `'As of transformers v4.44, default chat template is no longer allowed, so you must provide a chat template if the tokenizer does not define one.'`

`cpatonn/Qwen3-Coder-30B-A3B-Instruct-AWQ-4bit` community repo's `tokenizer_config.json` does not ship a `chat_template` field. vLLM refuses to format messages without one.

**Three fix options** (most to least recommended):

| Option | Approach | Rebuild cost | Notes |
|---|---|---|---|
| **A (recommended)** | Update `services/model-server/scripts/fetch_weights.py` to also pull `tokenizer_config.json` (or `chat_template.jinja`) from `Qwen/Qwen3-Coder-30B-A3B-Instruct` official repo and overlay onto the AWQ weight dir. | One Cloud Build + apply cycle | Minimal code change; keeps template coupled to weights; self-contained. |
| **B** | Pass `--chat-template <path>` to vLLM in `entrypoint.sh`; bake template file at a known location in the image. | One Cloud Build + apply cycle | Slightly more brittle — decouples template from weights. |
| **C** | Switch AWQ repo to one that ships the template. | Research + one Cloud Build + apply cycle | Biggest change; needs research on available AWQ variants for Qwen3-Coder-30B-A3B-Instruct. |

### What's in-flight / caveats

- **Pre-existing Python CI lint failure on main** (PR #9 — import-sorting + unused symbols in `services/coder-agent/src/coder_agent/agent.py`). Every PR this session required admin bypass. Needs cleanup before the next feature cycle.
- **L4 is no-zonal-redundancy only.** GCP denied the zonal-redundant variant. Single-zone, POC-acceptable per ADR-0014. Quota retry scheduled for ~1 week out.
- **Stale local branch** `chore/redact-for-public-release` — billing ID in history, remote gone, safe to delete.
- **GitHub `refs/pull/{1..4}/head`** still leak billing ID from pre-2026-04-21 orphan-squash era. Documented plan for a future session (nuclear delete + recreate); not in-repo.

### Deferred (not blocking MVP)

- **503-during-load contract test** on model-server `/health` (qa-engineer; requires mocking vLLM startup phases).
- `_GoogleIdTokenAuth` auth ADR (carried over).
- `pythonjsonlogger.jsonlogger` deprecation warning (carried over — trivial).

### Open questions for the next session

- Is tool-use (file read/write, shell) the next feature on top of the DeepAgents graph, or do we stabilize single-turn-with-planning first?
- Should we gate the model-server with a warmup ping to mask cold-start latency for demos?
- Option A vs B for the chat-template fix: is keeping the template coupled to the weight dir important, or is a separate baked-in template file acceptable?

### Cost-to-date

- Idle: ~£0.10/mo (AR repo + state bucket).
- L4 active: ~£0.72/hr (approx). Full day warm ≈ £17; POC usage 2–4 hrs/day ≈ £1.50–3.00/day.
- Kill-switch armed at £500 GBP billing-account cap.
- Cloud Build this session: ~46 min total (two builds). AR storage added: ~15 GiB (one new image; PR #18 replaced the prior digest).

### Hand-off plan

- `ml-engineer` — owns chat-template fix (options A/B/C above); primary next action.
- `devops-engineer` — fix Python lint failure on main to unblock normal PR merges.
- `qa-engineer` — 503-during-load contract test (deferred); wire live-chat smoke test into CI behind an env gate.
- `doc-keeper` — write carried-over `_GoogleIdTokenAuth` ADR.
- `orchestrator` — coordinates if post-fix smoke test surfaces cross-cutting issues.

---

## Archive

### 2026-04-22 — deployed, awaiting tool-choice rebuild

PRs #11–#18 merged (all admin-bypassed due to a pre-existing Python CI lint failure on main from PR #9). All three services live in `europe-west4`.

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

State at close: Cloud Build `bc7nzpahm` rebuilding model-server with PR #18 tool-choice fix; `terraform apply` pending; L4 no-zonal-redundancy only; Python CI lint failure on main blocking normal merges.

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
