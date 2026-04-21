########################################################################
# main.tf — root composition
#
# Single-region deployment (ADR-0014 supersedes ADR-0011 regional split):
#   Both coder-agent and model-server (GPU) run in var.region (europe-west4).
#   L4 Cloud Run GPU is GA in europe-west4 — no regional split needed.
########################################################################

module "artifact_registry" {
  source = "./modules/artifact_registry"

  project_id      = var.project_id
  region          = var.region
  repository_name = var.artifact_registry_repo
}

module "iam" {
  source = "./modules/iam"

  project_id = var.project_id
}

module "storage" {
  source = "./modules/storage"

  project_id         = var.project_id
  region             = var.region
  lifecycle_age_days = var.artifacts_bucket_lifecycle_age_days
}

########################################################################
# model-server -- GPU (NVIDIA L4), europe-west4 (ADR-0014)
#
# GPU QUOTA: Before apply, request quota in GCP Console:
#   IAM & Admin -> Quotas -> filter "Cloud Run" ->
#   "Total Nvidia L4 GPU allocation, per project per region" -> europe-west4
#   Request at least 1. Default for new projects is 0.
########################################################################
module "model_server" {
  source = "./modules/cloud_run_gpu"

  project_id      = var.project_id
  region          = var.region
  service_name    = "model-server"
  image           = var.model_server_image
  service_account = module.iam.model_server_sa_email

  gpu_enabled = var.model_server_gpu_enabled
  gpu_type    = var.model_server_gpu_type

  cpu             = var.model_server_cpu
  memory          = var.model_server_memory
  min_instances   = var.model_server_min_instances
  max_instances   = var.model_server_max_instances
  concurrency     = var.model_server_concurrency
  timeout_seconds = var.model_server_timeout_seconds

  # vLLM cold start: CUDA init + AWQ model load + warmup ~20-60s (ADR-0011).
  # initial_delay=60 + period=10 * failure_threshold=12 -> up to 180s total probe window.
  startup_probe_initial_delay     = 60
  startup_probe_period            = 10
  startup_probe_failure_threshold = 12
  startup_probe_timeout           = 10

  env = {
    # PORT is set by Cloud Run automatically; vLLM reads it via entrypoint.sh.
    # SERVED_MODEL_NAME must match the coder-agent's MODEL_NAME
    # (coder-agent/src/coder_agent/config.py). Both sides default to the
    # full HF id; mismatch causes vLLM to 404 /v1/chat/completions.
    SERVED_MODEL_NAME = "Qwen/Qwen3-Coder-30B-A3B-Instruct"
    # max_model_len must be validated by ml-engineer on real L4 before deploy
    # (ADR-0013). Default 32768 -- reduce to 16384 or 24576 if KV cache
    # exceeds VRAM headroom.
    MAX_MODEL_LEN = "32768"
  }

  # Only the coder-agent SA can invoke (CLAUDE.md s3.4 -- no allUsers without ADR).
  invoker_members = [
    "serviceAccount:${module.iam.coder_agent_sa_email}",
  ]
}

module "coder_agent" {
  source = "./modules/cloud_run"

  project_id      = var.project_id
  region          = var.region
  service_name    = "coder-agent"
  image           = var.coder_agent_image
  service_account = module.iam.coder_agent_sa_email

  cpu             = var.coder_agent_cpu
  memory          = var.coder_agent_memory
  min_instances   = var.coder_agent_min_instances
  max_instances   = var.coder_agent_max_instances
  concurrency     = var.coder_agent_concurrency
  timeout_seconds = var.coder_agent_timeout_seconds

  env = {
    MODEL_SERVER_URL      = module.model_server.url
    MODEL_SERVER_AUDIENCE = module.model_server.url
    GCP_PROJECT_ID        = var.project_id
    ARTIFACTS_BUCKET      = module.storage.artifacts_bucket_name
    LOG_LEVEL             = "INFO"
    # GPU cold start ~20-60s + request processing. Keep generous.
    REQUEST_TIMEOUT_SECONDS = "300"
  }

  # For POC/MVP: developer invokes via ID token. Keep private.
  # To open to the world, add an ADR first.
  invoker_members = var.coder_agent_invoker_members

  depends_on = [module.model_server]
}

# Budget alerts
# GPU (L4) cost profile: ~$0.90/hr per instance when warm.
# At 8 active hrs/day -> ~$220/mo. Budget raised to $300 to cover
# active MVP usage with headroom. Threshold is in var.monthly_budget_usd.
# See setup-billing-alerts.sh and modules/budget/main.tf.
module "budget" {
  source = "./modules/budget"

  project_id         = var.project_id
  billing_account_id = var.billing_account_id
  monthly_budget_usd = var.monthly_budget_usd
  alert_emails       = var.budget_alert_emails
}
