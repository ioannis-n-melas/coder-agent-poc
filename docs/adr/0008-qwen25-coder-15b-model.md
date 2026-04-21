# 0008 — Qwen2.5-Coder-1.5B-Instruct as POC model

- **Status**: Superseded by [ADR-0013](0013-qwen3-coder-30b-a3b-instruct-model.md)
- **Date**: 2026-04-19
- **Authors**: @ioannis-n-melas

## Context

Small model, CPU-usable, code-specialized, permissive license. Needs to fit in ~4 GiB Cloud Run memory budget with some headroom.

## Options considered

| Model | Size (Q4) | License | Notes |
|---|---|---|---|
| Qwen2.5-Coder-0.5B-Instruct | ~400 MB | Apache 2.0 | Too small for anything non-trivial. |
| **Qwen2.5-Coder-1.5B-Instruct** | **~1.0 GB** | **Apache 2.0** | Sweet spot for 2 vCPU / 4 GiB. Good coder quality for size. |
| Qwen2.5-Coder-3B-Instruct | ~2.0 GB | Non-commercial research | License issue for production. |
| Llama-3.2-1B-Instruct | ~700 MB | Llama Community | Not code-specialized; weaker on code. |
| Llama-3.2-3B-Instruct | ~2.0 GB | Llama Community | Better quality, heavier. |
| DeepSeek-Coder-1.3B-Instruct | ~800 MB | MIT | Good coder, older architecture. |
| StarCoder2-3B | ~1.8 GB | BigCode OpenRAIL-M | Good coder, non-instruct baseline. |

## Decision

**Qwen2.5-Coder-1.5B-Instruct** (Q4_K_M GGUF from `bartowski/Qwen2.5-Coder-1.5B-Instruct-GGUF`).

- Best coder quality per byte at this size class.
- Apache 2.0 — commercial use OK.
- Instruction-tuned.
- Known-good OpenAI-compatible behavior under llama.cpp.

## Consequences

- **Good**: Fits comfortably in 4 GiB with 8 K context; leaves headroom for larger batches.
- **Bad**: 1.5B is noticeably weaker than 7B+ models. Expect ~60–70 % of 7B quality on code tasks.
- **Trigger to revisit**: (a) quality insufficient for real tasks (move up to 3B / 7B with GPU), (b) a better sub-2B coder model is released.

## References

- [Qwen2.5-Coder paper & models](https://github.com/QwenLM/Qwen2.5-Coder)
- [bartowski/Qwen2.5-Coder-1.5B-Instruct-GGUF on HF](https://huggingface.co/bartowski/Qwen2.5-Coder-1.5B-Instruct-GGUF)
