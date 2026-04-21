# syntax=docker/dockerfile:1.7
# ──────────────────────────────────────────────────────────────────────────
# model-server — vLLM serving Qwen3-Coder-30B-A3B-Instruct (AWQ int4) on L4.
#
# Design notes:
#   * Contract (ADR-0001): exposes OpenAI-compatible HTTP on ${PORT}. The
#     agent does NOT care that vLLM is the backend — swapping runtimes is
#     URL-only from the agent's POV.
#   * Runtime is vLLM's published OpenAI server image. We do NOT rebuild vLLM
#     here; the published image is the tested, known-good artifact.
#   * Weights are baked in (see docs/adr/0011-cloud-run-l4-gpu.md + the
#     fetch_weights.py docstring for why).
#   * Non-root runtime user (CLAUDE.md §3.3).
# ──────────────────────────────────────────────────────────────────────────

# --------------------------------------------------------------------------
# Stage 1: download the AWQ weights into a throwaway layer.
#
# Kept as a separate stage so that:
#   (1) the ~17 GiB weight fetch does NOT invalidate the runtime image cache
#       on unrelated code changes,
#   (2) the HF toolchain + curl + python stdlib we pull in here never reach
#       the runtime image.
# --------------------------------------------------------------------------
FROM python:3.12-slim AS weight-downloader

ARG MODEL_HF_REPO=cpatonn/Qwen3-Coder-30B-A3B-Instruct-AWQ-4bit
ARG MODEL_TARGET_DIR=/models/qwen3-coder-30b-a3b-instruct-awq

ENV MODEL_HF_REPO=${MODEL_HF_REPO} \
    MODEL_TARGET_DIR=${MODEL_TARGET_DIR} \
    HF_HUB_ENABLE_HF_TRANSFER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# hf_transfer makes parallel-chunked downloads an order of magnitude faster
# for the multi-GB weight shards. huggingface_hub is pinned to a recent,
# known-good floor (0.27). These two are the ONLY python deps needed at
# bake time — no vLLM, no torch.
RUN pip install --no-cache-dir \
        "huggingface-hub>=0.27,<1.0" \
        "hf-transfer>=0.1.9,<1.0"

WORKDIR /fetch
COPY scripts/fetch_weights.py /fetch/fetch_weights.py

# Optional HF token for gated repos. Passed via `--secret id=hf_token,...`
# so it never ends up in an image layer. Defaults to empty (public repos).
RUN --mount=type=secret,id=hf_token,required=false \
    HF_TOKEN="$(cat /run/secrets/hf_token 2>/dev/null || true)" \
    python /fetch/fetch_weights.py

# --------------------------------------------------------------------------
# Stage 2: runtime — vLLM's official OpenAI-compatible server image.
#
# Pin the exact tag. `:latest` would be a silent version drift vector on
# every rebuild.
# --------------------------------------------------------------------------
FROM vllm/vllm-openai:v0.19.1-ubuntu2404 AS runtime

# Non-root runtime user. The published vllm image runs as root; we override.
# UID 10001 matches the convention used by the sibling coder-agent service.
RUN groupadd --system --gid 10001 vllm \
 && useradd  --system --uid 10001 --gid 10001 --home-dir /home/vllm --create-home vllm

# Copy the baked weights from stage 1. Ownership set to the non-root user so
# vLLM can read them without any chmod dance at runtime.
COPY --from=weight-downloader --chown=vllm:vllm \
     /models/qwen3-coder-30b-a3b-instruct-awq \
     /models/qwen3-coder-30b-a3b-instruct-awq

# Entrypoint script. `set -euo pipefail` inside the script; +x here.
COPY --chown=vllm:vllm entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Default caches under the vllm user's home so we don't try to write to root-
# owned directories at runtime.
ENV HOME=/home/vllm \
    HF_HOME=/home/vllm/.cache/huggingface \
    XDG_CACHE_HOME=/home/vllm/.cache \
    # vLLM/pytorch will fail fast rather than warn on unknown kwargs.
    TRANSFORMERS_VERBOSITY=warning \
    # hf_transfer at bake time only; at runtime we never hit HF.
    HF_HUB_OFFLINE=1 \
    # vLLM honours these but they can also be overridden by entrypoint.sh flags.
    VLLM_WORKER_MULTIPROC_METHOD=spawn

# Cloud Run supplies PORT; pick a sane default for docker-compose / local.
EXPOSE 8080
USER vllm

# vLLM's published image has its own ENTRYPOINT; override to our shim.
ENTRYPOINT ["/entrypoint.sh"]
CMD []
