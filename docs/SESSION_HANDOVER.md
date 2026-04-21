# Session handover

> **Purpose**: the fastest path back into flow for the next contributor (human or agent). Update this at the end of every working session. Read it at the start of every session.

---

## Current state — 2026-04-20 (end-to-end POC working)

### What's landed

- **`/chat` is unblocked.** A deployed POST to `coder-agent` /chat returns 200 with non-empty output. Verified via `./scripts/smoke-test.sh` on the live Cloud Run services.
  - Sample: prompt `"Write a Python hello world. Return code only, no explanation."` → `"```python\nprint(\"Hello, World!\")\n```"`.
- **DeepAgents stripped from the POC chat path.** Replaced `deepagents.create_deep_agent` with a plain `ChatOpenAI` chat loop in `services/coder-agent/src/coder_agent/agent.py`. See [ADR 0009](adr/0009-strip-deepagents-for-poc-chat.md) for why, and the trigger to bring it back.
- **`_GoogleIdTokenAuth` preserved.** Private-Cloud-Run-to-private-Cloud-Run auth is unchanged — it was always the load-bearing piece, not the agent framework.
- **Both services deployed** at the same URLs as before:
  - `coder-agent` → https://coder-agent-5eiztln6kq-ez.a.run.app (new revision, image `coder-agent@sha256:c4c22115faa0…`)
  - `model-server` → https://model-server-5eiztln6kq-ez.a.run.app (revision unchanged; image digest untouched)
  - Both remain private (`--no-allow-unauthenticated`); `coder-agent-sa` still has `run.invoker` on model-server. Both still `min_instances=0`.
- **22/22 unit tests pass.** Ruff lint + format clean. `uv.lock` regenerated — dropped 9 transitive deps (deepagents, langgraph, anthropic, langchain-anthropic, google-genai, langchain-google-genai, docstring-parser, filetype, bracex, wcmatch).

### What's in-flight

- Nothing actively broken. POC bar met.
- **Open PR #1** (`deploy/first-cloud-run-deploy`) still hasn't been merged — user decision. This session's work lives on `feat/strip-deepagents-for-poc`, stacked on that PR, and **not yet pushed or PR'd**. The parent agent will push + PR after reviewing the diff.

### Changes made this session (code, infra, scripts, docs)

1. **`services/coder-agent/src/coder_agent/agent.py`** — removed `deepagents.create_deep_agent`; new `ChatAgent` class wraps `ChatOpenAI` and exposes `ainvoke({"messages":[...]}) → {"messages":[<AIMessage>]}` so `main.py` doesn't have to change. `_GoogleIdTokenAuth` untouched. System prompt trimmed to one sentence.
2. **`services/coder-agent/tests/test_agent.py`** — kept all 4 `_GoogleIdTokenAuth` tests and the 4 `build_chat_model` tests. Added 4 new tests covering `ChatAgent.ainvoke` with a fake model (round-trip, caller-supplied system message, assistant turns ignored, `build_agent` returns a `ChatAgent`).
3. **`services/coder-agent/pyproject.toml`** — removed `deepagents>=0.0.5` and `langgraph>=0.2.50` direct deps. Removed `deepagents.*` from the mypy overrides. Description updated.
4. **`services/coder-agent/uv.lock`** — regenerated. 9 transitive deps dropped.
5. **`services/coder-agent/README.md`** — description updated, stale `/plan` endpoint removed, POC note pointing at ADR 0009 added.
6. **`docs/adr/0009-strip-deepagents-for-poc-chat.md`** — new ADR. Documents context (the `content: null` vs Hermes-2-Pro Jinja mismatch), 4 options considered, decision, what we kept, trigger to revisit.
7. **`docs/adr/0003-deepagents-as-agent-framework.md`** — status header updated to `Partially superseded by #0009`. Body unchanged.
8. **`docs/DECISIONS.md`** — index updated (0003 status, 0009 added).
9. **`infra/terraform/terraform.tfvars`** — `coder_agent_image` digest bumped to `sha256:c4c22115faa0…`. File is gitignored.

### Next actions (in priority order)

1. **Merge PR #1**, then push this branch (`feat/strip-deepagents-for-poc`), open PR #2 against main. Owner: user.
2. **ADR for the Google ID-token auth wiring.** How audience is derived, how ADC works locally, how the metadata server mints for `coder-agent-sa`. Owner: `doc-keeper` + `tech-lead`. Carried over from the 2026-04-20 block.
3. **Slow integration test** against live `/chat` (`@pytest.mark.slow`, gated on an env flag so CI doesn't depend on GCP). Owner: `qa-engineer`. Carried over.
4. **Make `/ready` more forgiving on cold starts.** Current 5 s timeout fires during a cold model-server start (~10 s for image, +30 s for first prompt). Either bump the timeout to ~15 s or make readiness only verify DNS + IAM, not full `/health` round-trip. Low priority — `/chat` itself works, this is just the probe's truthfulness.
5. **Pin image tags instead of digests** in `terraform.tfvars` once we have a SHA-based tag convention. Readability win. Owner: `devops-engineer`.
6. **Fix the `pythonjsonlogger` deprecation warning.** `pythonjsonlogger.jsonlogger` → `pythonjsonlogger.json`. Trivial.

### Open questions for the next session

- Is the next feature "tools come back" or "multi-turn memory" or "second model (bigger context)"? The answer determines whether we bring DeepAgents back or design our own LangGraph.
- Do we want to commit `terraform.tfvars` into the repo after all? Digests are the source of truth for what's deployed and losing them across machines is painful. The secret is only the billing account ID which isn't really a secret. Consider `terraform.tfvars` in VCS with secrets moved to a separate `*.auto.tfvars` that's gitignored.

### Known issues / gotchas

- **`/ready` may return `degraded` on the first request after 15+ min idle.** Model-server cold start takes longer than the probe's 5 s timeout. `/chat` self-heals (it has a 300 s timeout); `/ready` will flip to `ok` as soon as the model-server is warm. See next-action #4.
- **`openai` SDK retries twice on 500s.** If you see three stacktraces for one request in logs, that's why.
- **Deploys always touch the `model-server` resource** because of an empty `scaling {}` block in the old state. This apply cleaned it up on both services, so the next plan should show zero drift if no image changes.
- **User-account identity token still passes model-server's IAM check somehow.** Not blocking; worth investigating if we ever tighten authZ. Carried over from the 2026-04-20 block.

### Cost-to-date

- One coder-agent rebuild + push (small image, ~minutes of build, ~MB of registry egress) — negligible.
- One Cloud Run revision roll on each service. Zero min-instances, still scale-to-zero when idle.
- Smoke test: one cold start + one `/chat` request + a couple of `/health` probes. Under $0.01.
- **Project still sits at ~$0.10–$0.20/mo at idle.**

### Hand-off plan

Same as the previous block. Sub-agent team owns follow-up (see `.claude/agents/`):

1. `doc-keeper` + `tech-lead` own the ID-token-auth ADR (carried over).
2. `qa-engineer` owns the slow integration test (carried over).
3. `devops-engineer` on call for tfvars → tagged-image migration and cold-start `/ready` fix.
4. `ml-engineer` owns bringing tool use back — next time, with a runtime that can keep up (vLLM / Qwen tool calling, or LangGraph with bespoke tool shaping).
5. `orchestrator` coordinates when the work spans specialists.

---

## How to use this file

1. **Start of session**: read "Current state" top-to-bottom. Decide what to work on based on "Next actions".
2. **During session**: if you make a decision worth recording, write an ADR in `docs/adr/`.
3. **End of session**: replace the dated block above with a fresh one. Move the previous block into the archive section below if it has history worth keeping. Keep only the last 2–3 in-line; archive older ones.

---

## Archive

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
