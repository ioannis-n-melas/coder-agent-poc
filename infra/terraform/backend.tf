# Backend config is passed via `terraform init -backend-config=...` (see scripts/deploy.sh).
# The state bucket is created one-time by scripts/bootstrap-gcp.sh — it can't live in Terraform
# state itself (chicken-and-egg).

terraform {
  backend "gcs" {
    # bucket = "<project-id>-tfstate"    # provided by -backend-config
    # prefix = "terraform/state"         # provided by -backend-config
  }
}
