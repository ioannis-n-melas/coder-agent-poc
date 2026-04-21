#!/usr/bin/env bash
# Build and push Docker images to Artifact Registry.
#
# Usage:
#   ./scripts/build-and-push.sh                    # both services
#   ./scripts/build-and-push.sh model-server       # one service
#   ./scripts/build-and-push.sh coder-agent
#
# Tags with both the git SHA and the version from .env (MODEL_SERVER_IMAGE_TAG /
# CODER_AGENT_IMAGE_TAG).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
set -a; source "$REPO_ROOT/.env" 2>/dev/null || source "$REPO_ROOT/.env.example"; set +a

: "${GCP_PROJECT_ID:?}"
: "${GCP_REGION:?}"
: "${AR_REPO:?}"
: "${AR_HOST:?}"

GIT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")"
if git -C "$REPO_ROOT" diff --quiet HEAD -- 2>/dev/null; then
  DIRTY_SUFFIX=""
else
  DIRTY_SUFFIX="-dirty"
fi

build_push() {
  local svc="$1" version="$2"
  local ctx="$REPO_ROOT/services/$svc"
  local image_uri="${AR_HOST}/${GCP_PROJECT_ID}/${AR_REPO}/${svc}"

  echo ""
  echo "── $svc ────────────────────────────────────────────"
  echo "context : $ctx"
  echo "tag     : ${version} + sha-${GIT_SHA}${DIRTY_SUFFIX}"

  docker build \
    --platform linux/amd64 \
    --tag "${image_uri}:${version}" \
    --tag "${image_uri}:sha-${GIT_SHA}${DIRTY_SUFFIX}" \
    --tag "${image_uri}:latest" \
    "$ctx"

  docker push "${image_uri}:${version}"
  docker push "${image_uri}:sha-${GIT_SHA}${DIRTY_SUFFIX}"
  docker push "${image_uri}:latest"

  echo "✓ pushed ${image_uri}:${version}"
}

target="${1:-all}"

case "$target" in
  model-server)
    build_push model-server "${MODEL_SERVER_IMAGE_TAG:-v0.1.0}"
    ;;
  coder-agent)
    build_push coder-agent "${CODER_AGENT_IMAGE_TAG:-v0.1.0}"
    ;;
  all|"")
    build_push model-server "${MODEL_SERVER_IMAGE_TAG:-v0.1.0}"
    build_push coder-agent "${CODER_AGENT_IMAGE_TAG:-v0.1.0}"
    ;;
  *)
    echo "Unknown target: $target. Use: model-server | coder-agent | all"
    exit 1
    ;;
esac

echo ""
echo "✓ Build & push complete."
