#!/usr/bin/env bash
# One-time GCP bootstrap.
#
# - Enables APIs (idempotent)
# - Creates the Terraform state bucket
# - Configures gcloud to use the right project
#
# Re-run safely — every step is idempotent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env if present, else fall back to .env.example (warn)
if [[ -f "$REPO_ROOT/.env" ]]; then
  # shellcheck disable=SC1091
  set -a; source "$REPO_ROOT/.env"; set +a
else
  echo "⚠ No .env found. Copy .env.example to .env and fill in."
  echo "  Falling back to .env.example defaults (may not work for all values)."
  set -a; source "$REPO_ROOT/.env.example"; set +a
fi

: "${GCP_PROJECT_ID:?must be set}"
: "${GCP_REGION:?must be set}"

echo "Project : $GCP_PROJECT_ID"
echo "Region  : $GCP_REGION"
echo ""

# ── Set active project ─────────────────────────────────────────────
gcloud config set project "$GCP_PROJECT_ID" 1>/dev/null

# ── Enable APIs ────────────────────────────────────────────────────
echo "Enabling required APIs (idempotent)..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudbuild.googleapis.com \
  iam.googleapis.com \
  serviceusage.googleapis.com \
  cloudresourcemanager.googleapis.com \
  billingbudgets.googleapis.com \
  cloudbilling.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudfunctions.googleapis.com \
  pubsub.googleapis.com \
  eventarc.googleapis.com \
  --project="$GCP_PROJECT_ID"
# cloudfunctions.googleapis.com + pubsub.googleapis.com + eventarc.googleapis.com
# are required by the billing hard-cap kill-switch (ADR-0015).

# ── Create Terraform state bucket ──────────────────────────────────
TFSTATE_BUCKET="${GCP_PROJECT_ID}-tfstate"

if gsutil ls -b "gs://${TFSTATE_BUCKET}" >/dev/null 2>&1; then
  echo "✓ Terraform state bucket already exists: gs://${TFSTATE_BUCKET}"
else
  echo "Creating Terraform state bucket: gs://${TFSTATE_BUCKET}"
  gsutil mb -p "$GCP_PROJECT_ID" -l "$GCP_REGION" -b on "gs://${TFSTATE_BUCKET}"
  gsutil versioning set on "gs://${TFSTATE_BUCKET}"
  LIFECYCLE_TMP="$(mktemp)"
  cat >"$LIFECYCLE_TMP" <<'EOF'
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"numNewerVersions": 10}
    }
  ]
}
EOF
  gsutil lifecycle set "$LIFECYCLE_TMP" "gs://${TFSTATE_BUCKET}"
  rm -f "$LIFECYCLE_TMP"
fi

# ── Configure Docker auth for Artifact Registry (local push) ──────
echo "Configuring Docker auth for ${GCP_REGION}-docker.pkg.dev..."
gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet

echo ""
echo "✓ Bootstrap complete."
echo ""
echo "Next:"
echo "  1) cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars"
echo "     (edit values if needed — defaults should work)"
echo "  2) ./scripts/build-and-push.sh"
echo "  3) ./scripts/deploy.sh plan"
echo "  4) ./scripts/deploy.sh apply"
