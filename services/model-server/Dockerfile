# ──────────────────────────────────────────────────────────────────
# Stage 1: download the quantized GGUF model
# ──────────────────────────────────────────────────────────────────
FROM alpine:3.19 AS model-downloader
RUN apk add --no-cache curl ca-certificates

ARG MODEL_HF_REPO=bartowski/Qwen2.5-Coder-1.5B-Instruct-GGUF
ARG MODEL_FILE=Qwen2.5-Coder-1.5B-Instruct-Q4_K_M.gguf

WORKDIR /models
RUN curl -fL --retry 5 --retry-delay 5 \
    -o /models/model.gguf \
    "https://huggingface.co/${MODEL_HF_REPO}/resolve/main/${MODEL_FILE}" \
 && ls -lh /models/model.gguf

# ──────────────────────────────────────────────────────────────────
# Stage 2: runtime (llama.cpp server)
# Pinned tag — bump deliberately; unpinned :server drifts silently.
# ──────────────────────────────────────────────────────────────────
FROM ghcr.io/ggml-org/llama.cpp:server-b5350

COPY --from=model-downloader /models/model.gguf /models/model.gguf

ENV MODEL_PATH=/models/model.gguf \
    MODEL_CTX_SIZE=8192 \
    MODEL_THREADS=2

# Cloud Run supplies PORT. The upstream image sets ENTRYPOINT=["/app/llama-server"],
# so we override ENTRYPOINT to a shell form that can substitute ${PORT}.
# Non-root: the upstream image already uses a non-root user.
EXPOSE 8080

ENTRYPOINT ["sh", "-c", "exec /app/llama-server \
    --host 0.0.0.0 \
    --port ${PORT:-8080} \
    --model ${MODEL_PATH} \
    --ctx-size ${MODEL_CTX_SIZE} \
    --threads ${MODEL_THREADS} \
    --parallel 1 \
    --cont-batching \
    --jinja"]
CMD []
