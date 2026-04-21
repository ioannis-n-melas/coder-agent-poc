# 0009 — Strip DeepAgents for the POC chat path

- **Status**: Accepted — partially supersedes [#0003](0003-deepagents-as-agent-framework.md) for the Phase-1 POC only
- **Date**: 2026-04-20
- **Authors**: @ioannis-n-melas
- **Deciders**: @ioannis-n-melas

## Context

First deploy of both services to Cloud Run worked: `/health` and `/ready` pass
end-to-end, the Google ID-token auth path between `coder-agent` and
`model-server` is proven.

`/chat` returned **502** on every request. Root cause:

- `deepagents.create_deep_agent` wires in filesystem + subagents + todo
  middlewares by default. Every request posts a chat completion with a
  5,969-token system prompt containing OpenAI-format tool schemas.
- The assistant turn it generates contains `content: null` plus a
  structured `tool_calls` array.
- llama.cpp's Hermes-2-Pro Jinja template (enabled via `--jinja` to make
  tool-calling work at all) rejects `content: null` with
  `Expected 'content' to be a string or an array` → HTTP 500 from
  model-server → 502 bubbled out of `coder-agent`.

For the POC bar ("write a hello world end-to-end, from a deployed
service, through the full auth stack"), tool-calling is not required.
The forcing question is: do we unblock `/chat` in hours or days?

## Options considered

### Option A — Strip DeepAgents from the POC chat path (this ADR)
- Replace `create_deep_agent` with a plain `ChatOpenAI` chat completion loop.
- One system message + one user message → one assistant reply. No tools,
  no subagents, no middlewares.
- Keep `_GoogleIdTokenAuth` untouched — the whole point of the POC was
  to prove private-Cloud-Run-to-private-Cloud-Run auth, and that code
  is doing exactly what it should.
- **Cost**: ~1 hour to refactor + rebuild + redeploy. No infra changes.
- **Scope loss**: no planner/critic/refine loop, no tools. Explicitly
  out of scope for the POC milestone.

### Option B — Coerce `content: null` → `""` at the HTTP layer
- Subclass `ChatOpenAI` or attach an httpx event hook that mutates the
  request body before send.
- Keeps DeepAgents intact.
- **Cost**: ~2 hours, but fragile: we're patching around a framework
  contract that llama.cpp + DeepAgents disagree on. Next DeepAgents
  release could change payload shape.
- **Scope loss**: none.

### Option C — Swap to a chat template that accepts null content
- Drop `--jinja`, use `--chat-template chatml` explicitly.
- Tool-calling silently stops working at llama.cpp's template level,
  so DeepAgents' tool-calling path still breaks — we just move the
  failure mode.

### Option D — Swap runtimes to vLLM
- vLLM handles OpenAI tool-calling cleanly with Qwen2.5-Coder.
- Triggers the GKE phase — vLLM doesn't run on Cloud Run CPU gracefully.
- New ADR superseding [#0002](0002-llama-cpp-for-poc-model-server.md),
  new Terraform for GKE + KServe, budget impact.
- **Cost**: days of infra work. Wrong answer for "unblock `/chat` now."

## Decision

**Option A** — strip DeepAgents from the POC chat path. A single-turn
`ChatOpenAI` loop is sufficient to prove the deployed stack end-to-end
and is demonstrably the shortest path from broken to working.

We are not deprecating ADR 0003: DeepAgents remains the framework we
intend to bring back when the POC outgrows single-turn chat. This ADR
narrows its scope to "Phase 2 and later, once we have tools or a
tool-capable runtime."

### What we kept

- `_GoogleIdTokenAuth` + its wiring into `ChatOpenAI` via `http_client` /
  `http_async_client`. That's the only thing making private-model-server
  IAM work, and it's independent of DeepAgents.
- The `build_agent(settings)` → `ainvoke({"messages": [...]})` shape, so
  `main.py`'s FastAPI contract is unchanged (`ChatAgent` now provides
  the `ainvoke` method; `main.py` doesn't care who implements it).
- The `Settings` surface (`model_server_url`, `model_server_audience`,
  `request_timeout_seconds`, `temperature`, `max_tokens_per_response`,
  `model_name`).

### What we dropped

- `deepagents>=0.0.5` and `langgraph>=0.2.50` direct dependencies,
  plus all transitive deps (anthropic, langchain-anthropic,
  google-genai, langchain-google-genai, docstring-parser, filetype,
  bracex, wcmatch).
- The plan/analyze/implement/refine loop (it wasn't wired up yet —
  only the default DeepAgents middlewares were running).
- The verbose system prompt with coding-agent posture. Replaced with
  a 1-sentence "concise coding assistant" prompt.

## Consequences

- **Good**: `/chat` works. POC bar met.
- **Good**: smaller deploy surface — fewer transitive deps, faster
  container builds, fewer moving parts to debug while we prove the
  infra path.
- **Good**: chat template compatibility becomes a non-issue. If the
  model can chat, we can chat.
- **Bad**: no tool use. The agent can't read files, run commands, or
  plan across steps. If a user asks "refactor file X," the agent can
  only describe what it would do.
- **Bad**: DeepAgents integration knowledge is now un-exercised. When
  we bring it back we'll re-prove the wiring.
- **Trigger to revisit**: any of the following —
  1. We want the agent to actually touch code (read/write files, run
     tests) — forces a tool-capable loop back in.
  2. We add multi-turn dialog with memory of prior tool results.
  3. We move to a runtime that handles OpenAI tool-calling cleanly
     (vLLM, KServe with an instruct model). At that point, re-introduce
     DeepAgents or a thin LangGraph of our own. Write the new ADR with
     measurements (latency, cost, quality on a small golden set) before
     choosing.

## References

- [#0002 — llama.cpp as the POC model server](0002-llama-cpp-for-poc-model-server.md)
- [#0003 — DeepAgents as the agent framework](0003-deepagents-as-agent-framework.md)
- [#0008 — Qwen2.5-Coder-1.5B-Instruct as POC model](0008-qwen25-coder-15b-model.md)
- [deepagents on GitHub](https://github.com/langchain-ai/deepagents)
- [llama.cpp chat template docs](https://github.com/ggerganov/llama.cpp/blob/master/docs/server.md#chat-template)
