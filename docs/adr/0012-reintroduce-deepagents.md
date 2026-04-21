# 0012 — Re-introduce DeepAgents as agent framework

- **Status**: Accepted — supersedes [#0009](0009-strip-deepagents-for-poc-chat.md)
- **Date**: 2026-04-21
- **Authors**: @ioannis-n-melas
- **Deciders**: @ioannis-n-melas

## Context

This ADR must be read alongside [ADR-0003](0003-deepagents-as-agent-framework.md) and [ADR-0009](0009-strip-deepagents-for-poc-chat.md). Read those first.

**What happened:** ADR-0003 chose DeepAgents as the agent framework. ADR-0009 stripped it from the POC `/chat` path for concrete reasons:

1. `create_deep_agent` injected a 5,969-token system prompt with OpenAI tool schemas into every request.
2. The assistant response contained `content: null` with a `tool_calls` array.
3. llama.cpp's Jinja template rejected `content: null`, producing HTTP 500 → 502.
4. The POC bar was "prove the full auth stack end-to-end with a working `/chat`" — tool-calling was not in scope. The fastest fix was a plain `ChatOpenAI` loop.

ADR-0009 explicitly stated: "We are not deprecating ADR-0003: DeepAgents remains the framework we intend to bring back when the POC outgrows single-turn chat."

**What has changed for MVP:**

1. **The runtime changes.** vLLM ([ADR-0010](0010-vllm-as-model-server-runtime.md)) handles OpenAI tool-calling cleanly with Qwen3-Coder. The `content: null` failure that triggered ADR-0009 is a llama.cpp + Jinja template problem, not a DeepAgents problem. That failure mode is gone.
2. **The model changes.** Qwen3-Coder-30B-A3B-Instruct ([ADR-0013](0013-qwen3-coder-30b-a3b-instruct-model.md)) is instruction-tuned for agentic, multi-step coding tasks. The 1.5B POC model was too weak to produce reliable tool calls; planning with it would have been noise. At 30B (MoE), planning is productive.
3. **The scope broadens.** MVP ambition is "agent actually touches code" — read files, run tests, write patches. A single `ChatOpenAI` loop cannot do this. The plan → analyze → implement → refine loop is the point.

The three trigger conditions listed in ADR-0009 for re-introducing DeepAgents are all now satisfied:
- We want the agent to touch code (condition 1).
- We are moving to a runtime that handles tool-calling cleanly (condition 3).

## Options considered

### Option A — Re-introduce DeepAgents (this ADR)
- Pros: directly delivers the planner + subagents + virtual filesystem primitives needed for multi-step coding; consistent with ADR-0003's original intent; LangGraph underneath gives us graph-level control when we need it.
- Cons: re-adds the complexity that was removed in ADR-0009; deepagents is a young package with potential for breaking changes; more tokens per request (planning overhead); re-proving the wiring takes time.

### Option B — Build a thin LangGraph graph directly
- Pros: more control, no deepagents abstraction layer, less dependency churn risk.
- Cons: we write every node and edge ourselves; slower to get to a working plan/analyze/implement/refine loop; ADR-0003 already evaluated this path and chose DeepAgents over it for exactly this reason.

### Option C — Keep the single-turn ChatOpenAI loop, add tool-calling manually
- Pros: minimal change from POC.
- Cons: manually wiring tool-calling into a flat loop is reinventing what DeepAgents already provides; this path leads to building a worse version of DeepAgents.

### Option D — Switch to a different framework (CrewAI, AutoGen, Smolagents)
- Pros: potentially more active ecosystems in some dimensions.
- Cons: we have existing context in the LangGraph/LangChain ecosystem (ADR-0003, ADR-0009); switching frameworks resets all that learning; none of these have a clear advantage over DeepAgents + LangGraph for this workload.

## Decision

**Option A — re-introduce DeepAgents.** The reasons ADR-0009 stripped it are gone. The reasons ADR-0003 chose it still hold. The MVP ambition requires the planning machinery.

Specifics:
- Restore `deepagents` and `langgraph` as direct dependencies via `uv add`.
- Rebuild the `build_agent(settings)` factory on top of DeepAgents' planner + subagents + virtual filesystem.
- The `ainvoke({"messages": [...]})` shape is preserved — `main.py`'s FastAPI contract is unchanged.
- The `_GoogleIdTokenAuth` wiring is unchanged.
- Pin deepagents to a specific version in `uv.lock`; do not float on latest.

## Consequences

- **Good**: plan → analyze → implement → refine loop is available. The agent can read files, run tests, write patches.
- **Good**: consistent with the original architecture intent (ADR-0003).
- **Good**: ADR-0001 contract unaffected — DeepAgents talks to an OpenAI-compatible URL; swapping the backend is still a URL change.
- **Bad**: complexity re-introduced. The surface area of a DeepAgents request is larger; debugging failures requires understanding the LangGraph state machine.
- **Bad**: more tokens per request (planner system prompt + subagent prompts + tool call overhead). Token cost is higher than the single-turn POC.
- **Bad**: deepagents is a young package. Breaking changes are plausible between minor versions. Pinning in `uv.lock` is required; upgrading is a deliberate act, not automatic.
- **Bad**: the `content: null` failure from ADR-0009 will not recur with vLLM, but vLLM + DeepAgents integration is unproven in this repo — re-proving the wiring is a concrete cost.
- **Trigger to revisit**: (a) DeepAgents' abstractions fight us and we spend more time working around the framework than using it — switch to raw LangGraph (Option B above), (b) deepagents goes stale or is abandoned — migrate to raw LangGraph, (c) we need streaming or state controls DeepAgents doesn't expose.

## References

- [ADR-0003 — DeepAgents as the agent framework](0003-deepagents-as-agent-framework.md)
- [ADR-0009 — Strip DeepAgents for the POC chat path](0009-strip-deepagents-for-poc-chat.md) (superseded by this ADR)
- [ADR-0010 — vLLM as model server runtime](0010-vllm-as-model-server-runtime.md)
- [ADR-0013 — Qwen3-Coder-30B-A3B-Instruct as MVP model](0013-qwen3-coder-30b-a3b-instruct-model.md)
- [deepagents on GitHub](https://github.com/langchain-ai/deepagents)
- [LangGraph docs](https://langchain-ai.github.io/langgraph/)
