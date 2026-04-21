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

module "model_server" {
  source = "./modules/cloud_run"

  project_id      = var.project_id
  region          = var.region
  service_name    = "model-server"
  image           = var.model_server_image
  service_account = module.iam.model_server_sa_email

  cpu             = var.model_server_cpu
  memory          = var.model_server_memory
  min_instances   = var.model_server_min_instances
  max_instances   = var.model_server_max_instances
  concurrency     = var.model_server_concurrency
  timeout_seconds = var.model_server_timeout_seconds

  # llama.cpp mmap takes ~10s; give it room
  startup_probe_initial_delay = 20
  startup_probe_timeout       = 60

  env = {
    # PORT is auto-set by Cloud Run; llama.cpp Dockerfile reads it.
  }

  # Only the coder-agent SA can invoke
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
    # CPU inference of a 1.5B model + DeepAgents-sized prompt/tools schema
    # can take 2–4 min first-hit. Keep generous on the POC.
    REQUEST_TIMEOUT_SECONDS = "300"
  }

  # For POC: the developer invokes via ID token. Keep private.
  # To open to the world, add an ADR first and then add "allUsers" here.
  invoker_members = var.coder_agent_invoker_members

  depends_on = [module.model_server]
}

# Budget alerts removed — relying on billing-account-level alerts from the
# shared billing account (set via var.billing_account_id) instead of a
# project-scoped budget.
