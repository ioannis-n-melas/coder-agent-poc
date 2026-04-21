# ──────────────────────────────────────────────────────────────────
# Stage 1: builder — install deps with uv
# ──────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# uv: fast, reproducible Python package manager
COPY --from=ghcr.io/astral-sh/uv:0.5.8 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependency layer (cacheable)
COPY pyproject.toml uv.lock* README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy source
COPY src ./src

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ──────────────────────────────────────────────────────────────────
# Stage 2: runtime
# ──────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user
RUN useradd --create-home --uid 10001 appuser

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy virtualenv + source from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src

USER appuser

EXPOSE 8080

CMD ["sh", "-c", "uvicorn coder_agent.main:app --host 0.0.0.0 --port ${PORT:-8080} --no-access-log"]
