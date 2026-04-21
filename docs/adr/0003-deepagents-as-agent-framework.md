# 0003 — DeepAgents as the agent framework

- **Status**: Partially superseded by [#0009](0009-strip-deepagents-for-poc-chat.md) — DeepAgents is temporarily stripped from the POC `/chat` path. The framework decision stands for Phase 2 and beyond.
- **Date**: 2026-04-19
- **Authors**: @ioannis-n-melas

## Context

We need an agent framework that supports a plan → analyze → implement → refine workflow, works with an OpenAI-compatible endpoint, and is cheap to extend with tools and sub-agents.

## Options considered

### Option A — DeepAgents (langchain-ai/deepagents)
- Built on LangGraph, with an opinionated "deep agent" loop (planner + subagents + filesystem/virtual workspace).
- Matches what the reference article uses.
- Works with any LangChain chat model (including `langchain-openai` pointed at our model-server).

### Option B — LangGraph directly
- Max control, but you write every node, edge, and state yourself.
- Heavier lift for POC; easy to migrate to if we outgrow DeepAgents.

### Option C — Claude Agent SDK
- Designed around Claude specifically. Doesn't fit a self-hosted small-model story cleanly.

### Option D — CrewAI / AutoGen / others
- Role-based agent teams. More opinionated than we need; less control over the state graph.

## Decision

**Option A — DeepAgents.** Matches the article. Fast path to a working POC. Drops to LangGraph cleanly if we outgrow it.

## Consequences

- **Good**: plan/analyze/implement/refine loop with minimal code.
- **Good**: one framework for main agent and sub-agents (if we add them).
- **Bad**: locked to LangChain ecosystem; LangChain churns. Pin versions in `uv.lock`.
- **Trigger to revisit**: (a) DeepAgents' abstractions start fighting us, (b) we need streaming patterns or state controls DeepAgents doesn't expose, (c) the framework goes stale.

## References

- [deepagents on GitHub](https://github.com/langchain-ai/deepagents)
- [LangGraph docs](https://langchain-ai.github.io/langgraph/)
