#!/usr/bin/env bash
# Terraform wrapper — init + plan/apply/output/destroy.
#
# Usage:
#   ./scripts/deploy.sh init
#   ./scripts/deploy.sh plan
#   ./scripts/deploy.sh apply
#   ./scripts/deploy.sh output
#   ./scripts/deploy.sh destroy    # DANGEROUS — also need to set CONFIRM_DESTROY=yes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TF_DIR="$REPO_ROOT/infra/terraform"

# shellcheck disable=SC1091
set -a; source "$REPO_ROOT/.env" 2>/dev/null || source "$REPO_ROOT/.env.example"; set +a

: "${GCP_PROJECT_ID:?}"
TFSTATE_BUCKET="${GCP_PROJECT_ID}-tfstate"

cd "$TF_DIR"

action="${1:-plan}"

tf_init() {
  terraform init \
    -reconfigure \
    -backend-config="bucket=${TFSTATE_BUCKET}" \
    -backend-config="prefix=terraform/state"
}

# Ensure terraform.tfvars exists
if [[ ! -f "$TF_DIR/terraform.tfvars" ]]; then
  echo "⚠ terraform.tfvars not found — copying from example."
  cp "$TF_DIR/terraform.tfvars.example" "$TF_DIR/terraform.tfvars"
fi

case "$action" in
  init)
    tf_init
    ;;
  plan)
    tf_init
    terraform plan -out=tfplan
    ;;
  apply)
    tf_init
    if [[ -f tfplan ]]; then
      terraform apply tfplan
      rm -f tfplan
    else
      terraform apply
    fi
    ;;
  output)
    tf_init
    terraform output
    ;;
  destroy)
    if [[ "${CONFIRM_DESTROY:-}" != "yes" ]]; then
      echo "destroy requires CONFIRM_DESTROY=yes"
      exit 2
    fi
    tf_init
    terraform destroy
    ;;
  *)
    echo "Unknown action: $action. Use: init | plan | apply | output | destroy"
    exit 1
    ;;
esac
