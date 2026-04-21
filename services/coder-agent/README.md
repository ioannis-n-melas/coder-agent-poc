# coder-agent

DeepAgents-backed coder agent exposed via FastAPI. Implements a
**plan → analyze → implement → refine** pipeline. Talks to `model-server`
over an OpenAI-compatible HTTP endpoint (ADR-0001: swapping the backend
is a URL change only).

> **MVP (ADR-0012):** DeepAgents `0.5.3` is back. The root cause of
> [ADR-0009](../../docs/adr/0009-strip-deepagents-for-poc-chat.md)'s
> `content: null` failures (llama.cpp + Jinja) is gone — vLLM
> ([ADR-0010](../../docs/adr/0010-vllm-as-model-server-runtime.md))
> handles OpenAI tool-calling cleanly. The model is Qwen3-Coder-30B-A3B-Instruct
> ([ADR-0013](../../docs/adr/0013-qwen3-coder-30b-a3b-instruct-model.md)).

## Agent pipeline

```
User prompt
    │
    ▼
Orchestrator (planner)     ← create_deep_agent + ORCHESTRATOR_SYSTEM_PROMPT
    │
    ├─► analyzer subagent    ← reads + reports on relevant files
    │
    ├─► implementer subagent ← writes / edits code files
    │
    └─► refiner subagent     ← reviews, corrects, up to 3 passes
```

The orchestrator is the `create_deep_agent` graph itself; the three
stage-subagents are `SubAgent` specs registered via the `subagents=` kwarg.
DeepAgents' `SubAgentMiddleware` injects the `task` tool so the orchestrator
can delegate to them. All four components share the same `ChatOpenAI`
instance pointed at `MODEL_SERVER_URL`.

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

Or use `./scripts/dev.sh up` from the repo root to start both services via
docker compose.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness — verifies model-server reachable |
| POST | `/chat` | Run the plan→analyze→implement→refine loop. Returns JSON `{request_id, output}`. |

## Env vars

See [src/coder_agent/config.py](src/coder_agent/config.py) for the full list.

| Var | Default | Purpose |
|---|---|---|
| `MODEL_SERVER_URL` | — (required) | Base URL of the model-server (includes or implies `/v1`). |
| `MODEL_NAME` | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | Model id sent to the model-server; must match vLLM's `--served-model-name` (ADR-0013). |
| `MODEL_SERVER_AUDIENCE` | — (optional) | Cloud Run audience for Google ID-token auth. |
| `TEMPERATURE` | `0.2` | Sampling temperature. |
| `MAX_TOKENS_PER_RESPONSE` | `1024` | Max tokens per model response. |
| `REQUEST_TIMEOUT_SECONDS` | `120` | HTTP timeout for model-server calls. |
| `LOG_LEVEL` | `INFO` | |
| `ARTIFACTS_BUCKET` | — (optional) | GCS bucket for run artifacts. |

## Key files

| File | Purpose |
|---|---|
| `src/coder_agent/agent.py` | DeepAgents graph factory (`build_agent`), subagent specs, auth |
| `src/coder_agent/main.py` | FastAPI app — routes, lifespan, request/response models |
| `src/coder_agent/config.py` | Pydantic-settings config (`Settings`, `get_settings`) |
| `tests/test_agent.py` | Unit tests for agent factory, subagents, auth |
| `tests/test_integration.py` | FastAPI-layer integration tests (mock model) |
| `tests/test_main.py` | Route-level tests |
| `tests/test_config.py` | Config loading / URL normalisation tests |
