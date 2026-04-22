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

  # vLLM cold start on L4 (measured 2026-04-22 from first deploy attempt):
  #   CUDA init ~30s + weight load ~60s + model_runner init ~30s + graph
  #   capture (when enabled) ~30-60s + uvicorn bind ~5s. Total worst-case
  #   ~3 min. We use ENFORCE_EAGER=true (see env below) to skip graph
  #   capture — cuts cold start to ~2 min and frees ~1-2 GiB for KV cache.
  # initial_delay=60 + period=10 * failure_threshold=30 -> up to 360s probe window.
  # Extra margin is cheap (probes only run until first success).
  startup_probe_initial_delay     = 60
  startup_probe_period            = 10
  startup_probe_failure_threshold = 30
  startup_probe_timeout           = 10

  env = {
    # PORT is set by Cloud Run automatically; vLLM reads it via entrypoint.sh.
    # SERVED_MODEL_NAME must match the coder-agent's MODEL_NAME
    # (coder-agent/src/coder_agent/config.py). Both sides default to the
    # full HF id; mismatch causes vLLM to 404 /v1/chat/completions.
    SERVED_MODEL_NAME = "Qwen/Qwen3-Coder-30B-A3B-Instruct"
    # MAX_MODEL_LEN measured 2026-04-22 on real L4 (24 GiB VRAM):
    # 32768 fails with "KV cache needs 3.0 GiB, available 2.63 GiB.
    # Estimated max model length is 28672." 24576 gives headroom vs
    # vLLM's 28672 recommendation — safer against minor weight/driver
    # version drift. Trade-off: long-context tasks (>24k tokens) get
    # truncated. Revisit when we measure real request-length distribution.
    # ADR-0013 updated with measured values.
    MAX_MODEL_LEN = "24576"
    # The cpatonn/Qwen3-Coder-30B-A3B-Instruct-AWQ-4bit repo (ADR-0013) stores
    # its AWQ int4 weights under the compressed-tensors container format; its
    # config.json declares quantization_method=compressed-tensors. vLLM refuses
    # to start if the --quantization arg doesn't match that declaration, so we
    # override the entrypoint.sh default (awq_marlin). compressed-tensors still
    # routes W4A16 weights to the Marlin kernel on SM89+ — no perf loss.
    # Flip back to awq_marlin if we ever switch to a plain-AWQ repo.
    QUANTIZATION = "compressed-tensors"
    # Skip CUDA graph capture to cut cold-start time by ~30-60s. With
    # scale-to-zero every request risks a cold start, so faster boot
    # beats the ~10-20% steady-state throughput gain from graphs.
    # Revisit once we benchmark real agent loops and measure whether
    # throughput regression materially matters (RUNBOOK > Cold start).
    ENFORCE_EAGER = "true"
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

# Budget alerts (email-only, project-scoped)
# GPU (L4) cost profile: ~$0.90/hr per instance when warm.
# At 8 active hrs/day -> ~$220/mo. Budget raised to $300 to cover
# active MVP usage with headroom. Threshold is in var.monthly_budget_usd.
# See setup-billing-alerts.sh and modules/budget/main.tf.
# This budget is scoped to this project and sends email alerts only.
# It co-exists with module.billing_hard_cap (billing-account scope, kill-switch).
module "budget" {
  source = "./modules/budget"

  project_id         = var.project_id
  billing_account_id = var.billing_account_id
  monthly_budget_usd = var.monthly_budget_usd
  alert_emails       = var.budget_alert_emails
}

########################################################################
# Billing hard-cap kill-switch (ADR-0015)
#
# Billing-account-scoped budget at var.billing_hard_cap_amount GBP.
# When spend reaches 100% a Cloud Function (gen2) disables billing on
# EVERY project attached to the billing account.
#
# BLAST RADIUS: all projects on the billing account go dark.
# RECOVERY: gcloud billing projects link PROJECT_ID --billing-account=ACCOUNT_ID
#
# BEFORE FIRST APPLY: delete any manually-created UI budget named "total"
# (or any billing-account-scoped budget at ~500 GBP) so Terraform can
# own the canonical one without ambiguity.
#
# TARGETED APPLY (safe while model-server/coder-agent images are not yet
# pushed — avoids touching Cloud Run):
#   terraform apply -target=module.billing_hard_cap
########################################################################
module "billing_hard_cap" {
  source = "./modules/billing_hard_cap"

  project_id             = var.project_id
  region                 = var.region
  billing_account_id     = var.billing_account_id
  budget_amount          = var.billing_hard_cap_amount
  budget_currency_code   = var.billing_hard_cap_currency
  kill_threshold_percent = 1.0
}
