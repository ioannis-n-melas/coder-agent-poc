#!/usr/bin/env bash
# Local development helper.
#
# Usage:
#   ./scripts/dev.sh up            start both services via docker compose
#   ./scripts/dev.sh down          stop them
#   ./scripts/dev.sh logs          tail logs
#   ./scripts/dev.sh test          run pytest across services
#   ./scripts/dev.sh lint          ruff + mypy
#   ./scripts/dev.sh install       uv sync in each python service
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cmd="${1:-}"

case "$cmd" in
  up)
    docker compose -f "$REPO_ROOT/docker-compose.yml" up --build -d
    echo ""
    echo "Services:"
    echo "  model-server: http://localhost:${LOCAL_MODEL_SERVER_PORT:-8080}"
    echo "  coder-agent:  http://localhost:${LOCAL_CODER_AGENT_PORT:-8000}"
    echo ""
    echo "Tail logs: ./scripts/dev.sh logs"
    ;;
  down)
    docker compose -f "$REPO_ROOT/docker-compose.yml" down
    ;;
  logs)
    docker compose -f "$REPO_ROOT/docker-compose.yml" logs -f --tail=100
    ;;
  install)
    (cd "$REPO_ROOT/services/coder-agent" && uv sync)
    ;;
  test)
    (cd "$REPO_ROOT/services/coder-agent" && uv sync --quiet && uv run pytest -q)
    ;;
  lint)
    cd "$REPO_ROOT/services/coder-agent"
    uv sync --quiet
    uv run ruff check . --fix
    uv run ruff format --check .
    uv run mypy src
    ;;
  *)
    grep '^#' "$0" | sed 's/^# //' | head -n 10
    exit 1
    ;;
esac
