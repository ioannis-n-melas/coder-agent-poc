#!/usr/bin/env bash
# Launch vLLM's OpenAI-compatible API server for Qwen3-Coder-30B-A3B-Instruct (AWQ int4).
#
# Contract (ADR-0001): this script MUST result in an HTTP server that serves
#   GET  /health
#   GET  /v1/models
#   POST /v1/chat/completions
# on the port specified by the $PORT environment variable (Cloud Run requirement).
#
# All tunables here are exposed as env vars so that Terraform / docker-compose /
# local runs can override without rebuilding the image.

set -euo pipefail

# ---- required ------------------------------------------------------------
# $PORT is set by Cloud Run automatically; default 8080 for local runs.
PORT="${PORT:-8080}"

# Path where the weight-download stage copied the model. Bake-time constant,
# NOT user-tunable at runtime.
MODEL_DIR="${MODEL_DIR:-/models/qwen3-coder-30b-a3b-instruct-awq}"

# ---- agent-visible identity ---------------------------------------------
# The agent (services/coder-agent) addresses the model by this name in
# /v1/chat/completions requests. Keep it stable and independent of the
# underlying AWQ repo we pulled from — that way swapping between community
# AWQ builds never requires a coder-agent code change.
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-Qwen/Qwen3-Coder-30B-A3B-Instruct}"

# ---- vLLM serving tunables ----------------------------------------------
# awq_marlin is explicitly selected (rather than relying on vLLM's runtime
# auto-promotion from awq -> awq_marlin) because:
#   - L4 is Ada Lovelace (SM89); Marlin requires SM75+ and is substantially
#     faster than the reference AWQ kernel on decode.
#   - Being explicit documents intent and surfaces a load-time error if the
#     weight layout ever becomes Marlin-incompatible, rather than silently
#     falling back to the slow kernel.
# See docs/adr/0010-vllm-as-model-server-runtime.md.
QUANTIZATION="${QUANTIZATION:-awq_marlin}"

# 32768 per ADR-0013 proposal. L4 has 24 GiB VRAM; Qwen3-Coder-30B AWQ int4
# weights occupy ~17 GiB. That leaves ~6-7 GiB for KV cache, CUDA graph buffers,
# and activation workspace — enough for 32K context at the default batch size,
# tight but viable. If vLLM refuses to start with an OOM, ml-engineer must
# lower this (24576 then 16384) and update ADR-0013 via a note to doc-keeper.
MAX_MODEL_LEN="${MAX_MODEL_LEN:-32768}"

# MoE-active-param model — single request at a time is the MVP workload
# (coder-agent is the only client, see ADR-0012). We intentionally keep the
# KV-cache budget tight rather than pre-reserving memory for concurrent
# requests we will not serve.
MAX_NUM_SEQS="${MAX_NUM_SEQS:-4}"

# Fraction of VRAM vLLM is allowed to use. 0.90 leaves ~2.4 GiB for the CUDA
# runtime, driver overhead, and other processes. Going higher risks OOM during
# CUDA-graph capture; going lower wastes KV-cache budget.
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.90}"

# Disable CUDA graph capture if memory pressure forces it off. Default off
# (graphs on) for throughput; flip to "true" if we measure OOM at startup.
ENFORCE_EAGER="${ENFORCE_EAGER:-false}"

# ---- tool calling --------------------------------------------------------
# DeepAgents (ADR-0012) drives tool calls via OpenAI tool-choice semantics.
# vLLM requires --enable-auto-tool-choice + --tool-call-parser to accept
# tool_choice="auto" from the client, otherwise requests fail with 400.
# Qwen3-Coder uses the Hermes-style tool-call grammar (same as Qwen2.5).
ENABLE_TOOL_CHOICE="${ENABLE_TOOL_CHOICE:-true}"
TOOL_CALL_PARSER="${TOOL_CALL_PARSER:-hermes}"

# ---- assemble argv -------------------------------------------------------
ARGS=(
    --model "${MODEL_DIR}"
    --served-model-name "${SERVED_MODEL_NAME}"
    --host 0.0.0.0
    --port "${PORT}"
    --quantization "${QUANTIZATION}"
    --max-model-len "${MAX_MODEL_LEN}"
    --max-num-seqs "${MAX_NUM_SEQS}"
    --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}"
    --dtype auto
    --trust-remote-code
)

if [[ "${ENFORCE_EAGER}" == "true" ]]; then
    ARGS+=(--enforce-eager)
fi

if [[ "${ENABLE_TOOL_CHOICE}" == "true" ]]; then
    ARGS+=(--enable-auto-tool-choice --tool-call-parser "${TOOL_CALL_PARSER}")
fi

echo "[entrypoint] launching vLLM OpenAI server"
echo "[entrypoint]   served-model-name : ${SERVED_MODEL_NAME}"
echo "[entrypoint]   model-dir         : ${MODEL_DIR}"
echo "[entrypoint]   port              : ${PORT}"
echo "[entrypoint]   quantization      : ${QUANTIZATION}"
echo "[entrypoint]   max-model-len     : ${MAX_MODEL_LEN}"
echo "[entrypoint]   max-num-seqs      : ${MAX_NUM_SEQS}"
echo "[entrypoint]   gpu-mem-util      : ${GPU_MEMORY_UTILIZATION}"
echo "[entrypoint]   enforce-eager     : ${ENFORCE_EAGER}"
echo "[entrypoint]   tool-choice       : ${ENABLE_TOOL_CHOICE}"
echo "[entrypoint]   tool-call-parser  : ${TOOL_CALL_PARSER}"

exec python3 -m vllm.entrypoints.openai.api_server "${ARGS[@]}"
