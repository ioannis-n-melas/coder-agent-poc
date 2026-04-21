variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for regional resources"
  type        = string
  default     = "europe-west4"
}

variable "artifact_registry_repo" {
  description = "Name of the Artifact Registry repository for Docker images"
  type        = string
  default     = "coder-agent"
}

# ── model-server sizing ──────────────────────────────────────────────
variable "model_server_image" {
  description = "Full image URI for model-server (europe-west4-docker.pkg.dev/...)"
  type        = string
}

variable "model_server_cpu" {
  description = "Cloud Run CPU for model-server (string: 1, 2, 4, 8)"
  type        = string
  default     = "2"
}

variable "model_server_memory" {
  description = "Cloud Run memory for model-server"
  type        = string
  default     = "4Gi"
}

variable "model_server_min_instances" {
  description = "Minimum instances (0 = scale to zero)"
  type        = number
  default     = 0
}

variable "model_server_max_instances" {
  description = "Maximum instances"
  type        = number
  default     = 2
}

variable "model_server_concurrency" {
  description = "Max concurrent requests per instance"
  type        = number
  default     = 4
}

variable "model_server_timeout_seconds" {
  description = "Request timeout in seconds"
  type        = number
  default     = 300
}

# ── coder-agent sizing ──────────────────────────────────────────────
variable "coder_agent_image" {
  description = "Full image URI for coder-agent"
  type        = string
}

variable "coder_agent_cpu" {
  description = "Cloud Run CPU for coder-agent"
  type        = string
  default     = "1"
}

variable "coder_agent_memory" {
  description = "Cloud Run memory for coder-agent"
  type        = string
  default     = "1Gi"
}

variable "coder_agent_min_instances" {
  description = "Minimum instances"
  type        = number
  default     = 0
}

variable "coder_agent_max_instances" {
  description = "Maximum instances"
  type        = number
  default     = 3
}

variable "coder_agent_concurrency" {
  description = "Max concurrent requests per instance"
  type        = number
  default     = 8
}

variable "coder_agent_timeout_seconds" {
  description = "Request timeout in seconds"
  type        = number
  default     = 600
}

# ── artifacts bucket ────────────────────────────────────────────────
variable "artifacts_bucket_lifecycle_age_days" {
  description = "Delete artifacts older than N days"
  type        = number
  default     = 30
}

# ── budget ──────────────────────────────────────────────────────────
variable "monthly_budget_usd" {
  description = "Monthly budget cap for alerting (USD)"
  type        = number
  default     = 20
}

variable "billing_account_id" {
  description = "GCP billing account ID for budget alerts"
  type        = string
}

variable "budget_alert_emails" {
  description = "Emails to notify on budget alerts"
  type        = list(string)
  default     = []
}

# ── access control ──────────────────────────────────────────────────
variable "coder_agent_invoker_members" {
  description = "IAM members allowed to invoke the coder-agent Cloud Run service (e.g. [\"user:you@example.com\"]). Keep tight — opening to allUsers needs an ADR."
  type        = list(string)
}
