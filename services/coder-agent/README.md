# coder-agent

LangChain-based coder agent exposed via FastAPI. Talks to `model-server` over OpenAI-compatible HTTP.

> **Note (POC):** the current `/chat` runs a plain single-turn chat loop (no tools,
> no DeepAgents middlewares). See
> [docs/adr/0009-strip-deepagents-for-poc-chat.md](../../docs/adr/0009-strip-deepagents-for-poc-chat.md)
> for the trigger to re-introduce a tool-capable agent.

## Local development

```bash
cd services/coder-agent
uv sync                         # install deps + create .venv
uv run pytest                   # unit tests
uv run ruff check .             # lint
uv run mypy src                 # type check

# Run the service locally (requires a running model-server at MODEL_SERVER_URL)
MODEL_SERVER_URL=http://localhost:8080 \
  uv run uvicorn coder_agent.main:app --reload --port 8000
```

Or use `./scripts/dev.sh up` from the repo root to start both services via docker compose.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness — verifies model-server reachable |
| POST | `/chat` | Single-turn chat completion against the model-server. Returns JSON `{request_id, output}`. |

## Env vars

See [src/coder_agent/config.py](src/coder_agent/config.py) for the full list. Key ones:

| Var | Default | Purpose |
|---|---|---|
| `MODEL_SERVER_URL` | — (required) | Base URL of the model-server (includes or implies `/v1`). |
| `MODEL_NAME` | `qwen2.5-coder-1.5b` | Model name passed to OpenAI client (cosmetic for llama.cpp). |
| `LOG_LEVEL` | `INFO` | |
| `ARTIFACTS_BUCKET` | — (optional) | GCS bucket for run artifacts. |
