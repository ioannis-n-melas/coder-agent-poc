#!/usr/bin/env bash
# Build and push Docker images to Artifact Registry.
#
# Usage:
#   ./scripts/build-and-push.sh                    # both services
#   ./scripts/build-and-push.sh model-server       # model-server (GPU/vLLM image)
#   ./scripts/build-and-push.sh coder-agent        # coder-agent only
#
# Tags each image with both the semver tag and the git SHA:
#   <registry>/<project>/<repo>/<svc>:v<X.Y.Z>
#   <registry>/<project>/<repo>/<svc>:sha-<sha>
# No ':latest' in production pushes (CLAUDE.md rules).
#
# model-server (GPU image) build strategy:
#   The vLLM CUDA base image is ~10-15 GiB. Building locally on an M-series
#   Mac (linux/amd64 emulated) is extremely slow (~30-60 min). Cloud Build
#   runs on native amd64 and is the default for model-server. Set
#   USE_CLOUD_BUILD=false in .env to force a local Docker build (not
#   recommended for the GPU image).
#
#   Cloud Build tradeoff:
#     PRO: runs on native amd64, fast CUDA layer pulls from GCR, no local disk.
#     CON: Cloud Build charges ($0.003/build-min for n1-highcpu-8); large image
#          means ~10-20 min = ~$0.05-0.10 per build. Acceptable for MVP.
#
#   Local build tradeoff:
#     PRO: free, works offline.
#     CON: linux/amd64 QEMU emulation on Apple Silicon is slow; 15-30 min+.
#          Not recommended for the GPU image.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
set -a; source "$REPO_ROOT/.env" 2>/dev/null || source "$REPO_ROOT/.env.example"; set +a

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID must be set in .env}"
: "${GCP_REGION:?GCP_REGION must be set in .env}"
: "${AR_REPO:?AR_REPO must be set in .env}"
: "${AR_HOST:?AR_HOST must be set in .env}"

# Both services push to the same AR repo (ADR-0014 supersedes ADR-0011
# regional split — L4 Cloud Run GPU is GA in europe-west4).

GIT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")"
if git -C "$REPO_ROOT" diff --quiet HEAD -- 2>/dev/null; then
  DIRTY_SUFFIX=""
else
  DIRTY_SUFFIX="-dirty"
fi

# Whether to use Cloud Build for the model-server image.
# Strongly recommended for the vLLM/CUDA image (see header comment).
USE_CLOUD_BUILD="${USE_CLOUD_BUILD:-true}"

build_push_local() {
  local svc="$1" version="$2" registry_host="$3"
  local ctx="$REPO_ROOT/services/$svc"
  local image_uri="${registry_host}/${GCP_PROJECT_ID}/${AR_REPO}/${svc}"

  echo ""
  echo "── $svc (local build) ────────────────────────────────────────"
  echo "context  : $ctx"
  echo "registry : $registry_host"
  echo "tags     : ${version}, sha-${GIT_SHA}${DIRTY_SUFFIX}"

  docker build \
    --platform linux/amd64 \
    --tag "${image_uri}:${version}" \
    --tag "${image_uri}:sha-${GIT_SHA}${DIRTY_SUFFIX}" \
    "$ctx"

  docker push "${image_uri}:${version}"
  docker push "${image_uri}:sha-${GIT_SHA}${DIRTY_SUFFIX}"

  echo "  pushed ${image_uri}:${version}"
  echo "  pushed ${image_uri}:sha-${GIT_SHA}${DIRTY_SUFFIX}"
}

build_push_cloud_build() {
  local svc="$1" version="$2" registry_host="$3"
  local ctx="$REPO_ROOT/services/$svc"
  local image_uri="${registry_host}/${GCP_PROJECT_ID}/${AR_REPO}/${svc}"

  echo ""
  echo "── $svc (Cloud Build) ────────────────────────────────────────"
  echo "context  : $ctx"
  echo "registry : $registry_host"
  echo "tags     : ${version}, sha-${GIT_SHA}${DIRTY_SUFFIX}"
  echo "NOTE: Cloud Build charges ~\$0.003/min (n1-highcpu-8). Large CUDA"
  echo "      images take 10-20 min ~\$0.05-0.10 per build."

  gcloud builds submit \
    --project="${GCP_PROJECT_ID}" \
    --region="${CLOUD_BUILD_REGION:-europe-west4}" \
    --tag="${image_uri}:${version}" \
    --tag="${image_uri}:sha-${GIT_SHA}${DIRTY_SUFFIX}" \
    "$ctx"

  echo "  pushed ${image_uri}:${version}"
  echo "  pushed ${image_uri}:sha-${GIT_SHA}${DIRTY_SUFFIX}"
}

build_push_model_server() {
  local version="${MODEL_SERVER_IMAGE_TAG:-v0.2.0}"
  if [[ "${USE_CLOUD_BUILD}" == "true" ]]; then
    build_push_cloud_build "model-server" "$version" "$AR_HOST"
  else
    echo "WARNING: Building model-server locally. The vLLM CUDA image is ~10-15 GiB;"
    echo "         on Apple Silicon (QEMU emulation) this can take 30-60 min."
    echo "         Set USE_CLOUD_BUILD=true in .env to use Cloud Build instead."
    build_push_local "model-server" "$version" "$AR_HOST"
  fi
}

build_push_coder_agent() {
  local version="${CODER_AGENT_IMAGE_TAG:-v0.2.0}"
  build_push_local "coder-agent" "$version" "$AR_HOST"
}

target="${1:-all}"

case "$target" in
  model-server)
    build_push_model_server
    ;;
  coder-agent)
    build_push_coder_agent
    ;;
  all|"")
    build_push_model_server
    build_push_coder_agent
    ;;
  *)
    echo "Unknown target: $target. Use: model-server | coder-agent | all"
    exit 1
    ;;
esac

echo ""
echo "Build & push complete."
echo ""
echo "Update terraform.tfvars with the new image URIs before deploying:"
echo "  model_server_image = \"${AR_HOST}/${GCP_PROJECT_ID}/${AR_REPO}/model-server:${MODEL_SERVER_IMAGE_TAG:-v0.2.0}\""
echo "  coder_agent_image  = \"${AR_HOST}/${GCP_PROJECT_ID}/${AR_REPO}/coder-agent:${CODER_AGENT_IMAGE_TAG:-v0.2.0}\""
