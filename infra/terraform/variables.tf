variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for regional resources (coder-agent, artifact registry primary)"
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
  description = "Full image URI for model-server (us-central1-docker.pkg.dev/... for GPU). Must NOT use :latest."
  type        = string
}

# GPU is now the default for model-server (ADR-0011).
# L4 on Cloud Run mandates 8 vCPU / 32 Gi — do not reduce these.
variable "model_server_cpu" {
  description = "Cloud Run CPU for model-server. GPU (L4) requires '8'."
  type        = string
  default     = "8"
}

variable "model_server_memory" {
  description = "Cloud Run memory for model-server. GPU (L4) requires '32Gi' to hold Qwen3-30B-A3B AWQ weights (~16-18 GB) + KV cache headroom."
  type        = string
  default     = "32Gi"
}

variable "model_server_min_instances" {
  description = "Minimum instances (0 = scale to zero, ADR-0001 hard requirement). Temporarily set to 1 for demos — write an ADR before making permanent."
  type        = number
  default     = 0
}

variable "model_server_max_instances" {
  description = "Maximum instances. Capped at 1 until cost model justifies horizontal scaling (ADR-0011)."
  type        = number
  default     = 1
}

variable "model_server_concurrency" {
  description = "Max concurrent requests per instance. 1 recommended for GPU/vLLM at MVP scale to avoid VRAM pressure."
  type        = number
  default     = 1
}

variable "model_server_timeout_seconds" {
  description = "Per-request timeout in seconds."
  type        = number
  default     = 300
}

# ── model-server GPU config ──────────────────────────────────────────
variable "model_server_region" {
  description = "Region for the model-server GPU service. Must support NVIDIA L4 on Cloud Run (us-central1 confirmed per ADR-0011). Differs from var.region (europe-west4) — intentional regional split until Cloud Run GPU expands to europe-west4."
  type        = string
  default     = "us-central1"
}

variable "model_server_gpu_enabled" {
  description = "Attach NVIDIA L4 GPU to model-server. Set false only for CPU-only debugging; the vLLM image will not serve the Qwen3-30B model usably without GPU."
  type        = bool
  default     = true
}

variable "model_server_gpu_type" {
  description = "GPU accelerator type for model-server. Only 'nvidia-l4' is supported on Cloud Run as of 2026-04."
  type        = string
  default     = "nvidia-l4"
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
  description = "Monthly budget cap for alerting (USD). GPU (L4) changes the cost profile significantly: 1x L4 on Cloud Run costs ~$0.90/hr when warm. At 8 hrs/day active use that's ~$220/mo. Default raised to 300 USD to cover active MVP usage; lower it once you have a real usage baseline."
  type        = number
  default     = 300
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
