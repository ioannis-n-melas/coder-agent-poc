#!/usr/bin/env bash
# Set up / update billing budget alerts for the project.
#
# This script is idempotent -- re-running it updates the budget to the
# current values in terraform.tfvars (via terraform apply). It is
# a thin wrapper that ensures the billing APIs are enabled and then
# delegates to Terraform for the actual budget resource.
#
# GPU cost profile (why the threshold changed)
# POC (CPU, llama.cpp):  ~$5-20/mo at typical dev usage.
# MVP (GPU, L4 + vLLM):
#   - L4 on Cloud Run: ~$0.90/hr when the service is warm.
#   - With scale-to-zero: cost = active hours only (not 24/7).
#   - Estimate at 8 active hrs/day: ~$0.90 x 8 x 30 = $216/mo.
#   - With headroom for burst days and Artifact Registry storage: $300/mo.
#
# Default threshold: $300/mo.
#   Alerts fire at 50% ($150), 90% ($270), and 100% ($300).
#   If you expect lower usage (e.g. <2 hrs/day), lower monthly_budget_usd
#   in terraform.tfvars and re-run this script.
#
# To check current spend:
#   gcloud billing accounts list
#   gcloud alpha billing budgets list --billing-account=$GCP_BILLING_ACCOUNT
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
set -a; source "$REPO_ROOT/.env" 2>/dev/null || source "$REPO_ROOT/.env.example"; set +a

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID must be set in .env}"

echo "Project: $GCP_PROJECT_ID"
echo ""

# Ensure the Billing Budgets API is enabled (idempotent).
echo "Ensuring billing APIs are enabled..."
gcloud services enable \
  billingbudgets.googleapis.com \
  cloudbilling.googleapis.com \
  monitoring.googleapis.com \
  --project="$GCP_PROJECT_ID"

echo ""
echo "Billing APIs enabled."
echo ""
echo "Budget configuration is managed via Terraform (infra/terraform/modules/budget/)."
echo "The budget threshold is set in terraform.tfvars (monthly_budget_usd)."
echo "Default for GPU MVP: \$300/mo (see script header for rationale)."
echo ""
echo "Applying budget via Terraform..."
"$SCRIPT_DIR/deploy.sh" apply

echo ""
echo "Billing alerts configured. Alerts fire at 50% / 90% / 100% of monthly_budget_usd."
echo "To verify: gcloud alpha billing budgets list --billing-account=\$GCP_BILLING_ACCOUNT"
