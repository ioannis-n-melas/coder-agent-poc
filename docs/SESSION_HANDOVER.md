# Session handover

> **Purpose**: the fastest path back into flow for the next contributor (human or agent). Update this at the end of every working session. Read it at the start of every session.

---

## Current state — 2026-04-21 (pre-public-release hygiene pass)

### What's landed

- **Repo is ready to go public.** Audited working tree and **full git history** for credential leakage — clean on API keys, tokens, private keys. No `.env` / `*.tfvars` / `*.tfstate` / service-account JSON ever committed.
- **Two hygiene items fixed in code.** Hardcoded owner email as Cloud Run invoker → now driven by a new `coder_agent_invoker_members` list variable in [`infra/terraform/variables.tf`](../infra/terraform/variables.tf) (no default, forces explicit set). Billing-account ID baked into example files + docs → placeholders that point at `.env` / `terraform.tfvars` for the real values.
- **Git history squashed to a single commit.** The billing ID was baked into 4 pre-existing commits, so rather than a surgical `git-filter-repo` we did a full orphan-squash: `main` is now a single `chore: initial commit` (`9dd0308`). The surgical redaction PR (#4) was closed as superseded; remote feature branches deleted; branch protection on `main` restored after the one-time force-push.
- **Local backup tags kept**: `backup/pre-squash-main`, `backup/pre-squash-chore` point at the old history. Safe to delete with `git tag -d …` once you're confident nothing broke.
- **Terraform still validates.** Local gitignored `terraform.tfvars` has `coder_agent_invoker_members` populated, so the next `terraform apply` produces an identical Cloud Run IAM binding — zero behavior change.

### What's in-flight / caveats

- **GitHub preserves `refs/pull/{1..4}/head` on origin** pointing at the pre-squash commits (which contained the billing ID). These are *not* visible in `git log` of a clone but are fetchable by anyone who knows the PR number (`git fetch origin refs/pull/1/head`). **Accepted as low risk** — a billing-account ID is an opaque reference, not a credential, and can't be exploited without IAM. To fully purge would require deleting + recreating the GitHub repo; not worth the churn.
- **Nothing else in-flight.** Flipping repo visibility to public is a single click from the GitHub Settings page.

### Changes made this session (code, infra, docs)

1. [`infra/terraform/variables.tf`](../infra/terraform/variables.tf) — new `coder_agent_invoker_members` list variable (required, no default).
2. [`infra/terraform/main.tf`](../infra/terraform/main.tf) — Cloud Run invoker IAM binding driven by the variable; stale billing-ID comment genericized.
3. [`infra/terraform/terraform.tfvars.example`](../infra/terraform/terraform.tfvars.example) — generic placeholders (`your-project-id`, `XXXXXX-XXXXXX-XXXXXX`, `you@example.com`) with inline `gcloud billing accounts list` hint; added `coder_agent_invoker_members` example line.
4. [`.env.example`](../.env.example) — placeholder billing account + inline hint.
5. [`docs/RUNBOOK.md`](RUNBOOK.md) — owner / project / billing rows now point at `.env` / `terraform.tfvars`; the diagnostic `gcloud alpha billing accounts get-iam-policy` command reads `$GCP_BILLING_ACCOUNT` from `.env`.
6. `docs/SESSION_HANDOVER.md` (this file) — 2026-04-19 archive entry redacted of billing ID; fresh 2026-04-21 block.
7. `infra/terraform/terraform.tfvars` (gitignored, local-only) — `coder_agent_invoker_members = ["user:…"]` added.
8. **Git history rewrite** — orphan-squash to one root commit; `main` force-pushed; PR #4 closed; `chore/redact-for-public-release`, `deploy/first-cloud-run-deploy`, `feat/strip-deepagents-for-poc` removed from origin (the last two were already auto-deleted on merge).

### Next actions (in priority order)

1. **Flip repo visibility to public** on GitHub whenever you want. No further pre-flight blocked.
2. *(Optional)* Write an ADR documenting the history-squash decision — non-trivial per CLAUDE.md §2, currently only captured here. Owner: `doc-keeper`.
3. *(Carried over)* ADR for the Google ID-token auth wiring (`_GoogleIdTokenAuth`, audience derivation, ADC vs metadata server). Owner: `doc-keeper` + `tech-lead`.
4. *(Carried over)* Slow integration test against live `/chat` (`@pytest.mark.slow`, env-gated so CI doesn't depend on GCP). Owner: `qa-engineer`.
5. *(Carried over)* Make `/ready` more forgiving on cold starts (bump 5 s probe timeout to ~15 s, or decouple from full `/health` round-trip). Low priority.
6. *(Carried over)* Pin image tags instead of digests in `terraform.tfvars` once a SHA-tag convention is settled. Owner: `devops-engineer`.
7. *(Carried over)* Fix `pythonjsonlogger` deprecation warning: `pythonjsonlogger.jsonlogger` → `pythonjsonlogger.json`. Trivial.

### Open questions for the next session

- Is the next feature "tools come back" or "multi-turn memory" or "second model (bigger context)"? The answer determines whether DeepAgents returns or we design our own LangGraph.

### Known issues / gotchas (carried over)

- `/ready` may return `degraded` on first request after 15+ min idle — model-server cold start exceeds probe timeout. `/chat` self-heals (300 s timeout).
- `openai` SDK retries twice on 500s; three stacktraces in logs for one request is expected.
- Deploys used to always touch `model-server` due to a legacy empty `scaling {}` block — the last apply cleaned that up; next plan should be a no-op if no image digest changes.

### Cost-to-date

- Zero incremental GCP cost this session (no deploys, no registry pushes).
- **Project still sits at ~$0.10–$0.20/mo at idle.**

### Hand-off plan

Sub-agent team owns follow-up (see [`.claude/agents/`](../.claude/agents/)):

1. `doc-keeper` owns the history-squash ADR + the Google-ID-token-auth ADR.
2. `qa-engineer` owns the slow integration test.
3. `devops-engineer` on call for tfvars → tagged-image migration and cold-start `/ready` fix.
4. `ml-engineer` owns bringing tool use back (vLLM / Qwen tool calling, or bespoke LangGraph).
5. `orchestrator` coordinates when the work spans specialists.

---

## How to use this file

1. **Start of session**: read "Current state" top-to-bottom. Decide what to work on based on "Next actions".
2. **During session**: if you make a decision worth recording, write an ADR in [`docs/adr/`](adr/).
3. **End of session**: replace the dated block above with a fresh one. Move the previous block into the archive section below if it has history worth keeping. Keep only the last 2–3 in-line; archive older ones.

---

## Archive

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
