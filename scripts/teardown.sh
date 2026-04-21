#!/usr/bin/env bash
# Tear down Cloud Run services (keeps AR repo, state bucket, GCP project).
#
# Both services run in $GCP_REGION (europe-west4) per ADR-0014.
#
# For a full project delete, do it manually in the GCP console.
# This script is intentionally scoped to avoid destroying things that
# are expensive to recreate (state bucket, Artifact Registry, IAM).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
set -a; source "$REPO_ROOT/.env" 2>/dev/null || source "$REPO_ROOT/.env.example"; set +a

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID must be set in .env}"
: "${GCP_REGION:?GCP_REGION must be set in .env}"

echo "This will tear down:"
echo "  - Cloud Run service: coder-agent         (region: $GCP_REGION)"
echo "  - Cloud Run service: model-server (GPU)  (region: $GCP_REGION)"
echo "  - Service accounts: coder-agent-sa, model-server-sa"
echo "  - Artifacts bucket: ${GCP_PROJECT_ID}-artifacts"
echo "  - Artifact Registry repo: ${AR_REPO:-coder-agent}"
echo ""
echo "Keeps:"
echo "  - GCP project and billing link"
echo "  - Terraform state bucket (${GCP_PROJECT_ID}-tfstate)"
echo "  - APIs enabled"
echo ""
read -rp "Type 'teardown' to confirm: " confirm
if [[ "$confirm" != "teardown" ]]; then
  echo "Aborted."
  exit 1
fi

CONFIRM_DESTROY=yes "$SCRIPT_DIR/deploy.sh" destroy

echo ""
echo "Teardown complete. Re-deploy with ./scripts/deploy.sh apply."
