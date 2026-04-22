# 0013 — Qwen3-Coder-30B-A3B-Instruct as MVP model

- **Status**: Accepted — supersedes [#0008](0008-qwen25-coder-15b-model.md)
- **Date**: 2026-04-21
- **Authors**: @ioannis-n-melas
- **Deciders**: @ioannis-n-melas

## Context

ADR-0008 chose Qwen2.5-Coder-1.5B-Instruct (Q4_K_M GGUF) for the POC: small enough to fit on CPU in 4 GiB, adequate for a "hello world end-to-end" demo. ADR-0008 noted explicitly: "Trigger to revisit: quality insufficient for real tasks."

The MVP requires the agent to plan, analyze, implement, and refine code across multiple steps ([ADR-0012](0012-reintroduce-deepagents.md)). At 1.5B, the model is too weak for reliable tool calls, structured planning output, and multi-step agentic coding. Staying on 1.5B would produce an agent that fails on real tasks regardless of how well the infrastructure is built.

The design tenet from `CLAUDE.md` is "low cost first, optimize later." This ADR is a deliberate, bounded step up — not chasing the frontier, not maximizing benchmark scores.

**L4 VRAM budget:** 24 GB ([ADR-0011](0011-cloud-run-l4-gpu.md)). Any model choice must leave headroom for KV cache at the intended context length.

## Options considered

| Model | Type | VRAM (AWQ int4 approx) | Notes |
|---|---|---|---|
| **Qwen3-Coder-30B-A3B-Instruct** | MoE, 30B total / ~3B active | ~16–18 GB | Decode speed like a ~3B dense model; strong agentic coding; fits on L4 with KV headroom. |
| Qwen2.5-Coder-14B-Instruct | Dense | ~8–9 GB | Slower per-token than MoE active params; weaker tool-use than Qwen3-Coder; smaller gap from 1.5B quality-wise than the size jump implies. |
| DeepSeek-Coder-V2-Lite-16B | MoE, 16B total / 2.4B active | ~10 GB | Older architecture, weaker agentic coding vs Qwen3-Coder on SWE-bench class tasks. |
| Codestral-22B | Dense | ~13 GB | Strong coder, but weaker SWE-bench-agent score; dense means slower decode on L4 vs MoE. |
| Qwen3-Coder-32B-Instruct (dense) | Dense | ~20 GB | Too close to VRAM ceiling when combined with KV cache; no meaningful quality gain over the MoE variant for this workload. |

## Decision

**Qwen3-Coder-30B-A3B-Instruct, AWQ int4 quantization.**

Key reasons:
- MoE architecture: 30B total parameters, ~3B active per token. Decode speed is comparable to a ~3B dense model on L4, while quality is significantly higher. This is a latency win, not a memory win — MoE weights still occupy full VRAM (~16–18 GB), but the per-token compute is much lower.
- Strong agentic coding benchmark performance for the size class.
- Fits on L4 (24 GB) with headroom for KV cache at `max_model_len=32768`.
- AWQ int4 is natively supported by vLLM ([ADR-0010](0010-vllm-as-model-server-runtime.md)) — no conversion step.

Specifics:
- Model: `Qwen/Qwen3-Coder-30B-A3B-Instruct` (AWQ int4 variant from HuggingFace).
- Quantization: AWQ int4, loaded via `--quantization awq` in vLLM.
- Proposed `max_model_len`: 32768. **Measured on real L4 (2026-04-22)**: 32K fails with `KV cache needs 3.0 GiB, available 2.63 GiB. Estimated max is 28672.` With `ENFORCE_EAGER=true` (no CUDA graph buffers) and `gpu_memory_utilization=0.90`, the effective ceiling is ~28K. **Set `MAX_MODEL_LEN=24576`** in root `main.tf` to give headroom against driver/weight version drift. Revisit if real request-length distribution justifies pushing closer to the ceiling (or if `gpu_memory_utilization` is tuned up).
- AWQ quality note: int4 AWQ loses some precision vs BF16. Acceptable for coding tasks; if quality on a specific task class is insufficient, consider GPTQ or a larger active-parameter model.

## Consequences

- **Good**: capable of reliable tool calls and multi-step planning — unblocks the DeepAgents re-introduction ([ADR-0012](0012-reintroduce-deepagents.md)).
- **Good**: MoE decode speed means latency per token is roughly equivalent to a ~3B dense model on L4 — acceptable for interactive agentic use.
- **Good**: bounded cost increase from POC — deliberate step, not unbounded escalation.
- **Bad**: AWQ int4 loses quality vs BF16. On some tasks the quantization gap will be visible. GPTQ is an alternative if int4 AWQ proves insufficient.
- **Bad**: MoE is a latency win, not a memory win. All 30B parameters are loaded into VRAM even though only ~3B are active per forward pass. The L4's 24 GB is largely consumed by weights alone — context window sizing is constrained.
- **Bad**: VRAM budget is near-full. Context window (`max_model_len`) must be explicitly sized and validated. Increasing the context beyond ~32K is likely not possible on a single L4 without further quantization or model changes.
- **Bad**: per-request token cost is higher than the POC model when the service is warm. Each planning + tool-calling round trip will involve significantly more tokens than a single-turn chat.
- **Trigger to revisit**: (a) AWQ int4 quality is insufficient for a real coding task class — try GPTQ or a different quantization, (b) a new model is released that fits on L4 and materially improves agentic coding quality, (c) VRAM pressure forces `max_model_len` below 16K — reassess whether a smaller but denser model is a better fit.

## References

- [ADR-0008 — Qwen2.5-Coder-1.5B-Instruct as POC model](0008-qwen25-coder-15b-model.md) (superseded by this ADR)
- [ADR-0010 — vLLM as model server runtime](0010-vllm-as-model-server-runtime.md)
- [ADR-0011 — Cloud Run with NVIDIA L4 GPU for MVP serving](0011-cloud-run-l4-gpu.md)
- [ADR-0012 — Re-introduce DeepAgents as agent framework](0012-reintroduce-deepagents.md)
- [Qwen3-Coder model page (HuggingFace)](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct)
- [AWQ quantization — AutoAWQ](https://github.com/castor-ai/AutoAWQ)
