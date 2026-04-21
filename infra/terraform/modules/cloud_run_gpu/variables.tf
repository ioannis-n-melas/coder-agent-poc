########################################################################
# cloud_run_gpu/variables.tf
#
# Variables for the GPU-enabled Cloud Run v2 service module.
#
# GPU QUOTA NOTE:
#   Before terraform apply will succeed you must request a quota increase:
#   GCP Console -> IAM & Admin -> Quotas -> filter "Cloud Run" -> find
#   "Total Nvidia L4 GPU allocation, per project per region" in europe-west4
#   and request at least 1. Default quota is 0 for new projects.
#   URL: https://console.cloud.google.com/iam-admin/quotas
########################################################################

variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type        = string
  description = "Cloud Run region. Must be one that supports NVIDIA L4 (europe-west4 per ADR-0014)."
}

variable "service_name" {
  type        = string
  description = "Cloud Run service name"
}

variable "image" {
  type        = string
  description = "Full image URI including tag/digest. Must not be ':latest' in production."
}

variable "service_account" {
  type        = string
  description = "Service account email the container runs as"
}

# GPU config

variable "gpu_enabled" {
  type        = bool
  default     = true
  description = "Whether to attach a GPU. Set to false to redeploy on CPU only (e.g. for cost debugging). Requires the model image to support CPU fallback."
}

variable "gpu_type" {
  type        = string
  default     = "nvidia-l4"
  description = "GPU accelerator type. Only 'nvidia-l4' is supported on Cloud Run as of 2026-04."

  validation {
    condition     = contains(["nvidia-l4"], var.gpu_type)
    error_message = "Only 'nvidia-l4' is supported on Cloud Run. Update this validation when Cloud Run adds new GPU SKUs."
  }
}

variable "gpu_count" {
  type        = number
  default     = 1
  description = "Number of GPUs per instance. Cloud Run supports only 1 as of 2026-04."

  validation {
    condition     = var.gpu_count == 1
    error_message = "Cloud Run supports exactly 1 GPU per instance. Multi-GPU requires GKE."
  }
}

# Compute sizing
# L4 on Cloud Run requires 8 vCPU minimum (as of 2026-04, GPU services
# must use the matching CPU tier: 8 vCPU / 32 Gi).

variable "cpu" {
  type        = string
  default     = "8"
  description = "vCPU count. GPU Cloud Run requires 8. String form as required by Cloud Run."
}

variable "memory" {
  type        = string
  default     = "32Gi"
  description = "Memory. GPU Cloud Run with L4 requires 32Gi. Leaves ~6-8 GB headroom for KV cache on top of Qwen3-30B-A3B AWQ (~16-18 GB weights)."
}

# Scaling

variable "min_instances" {
  type        = number
  default     = 0
  description = "Minimum running instances. 0 = scale to zero (ADR-0001 hard requirement). Set to 1 temporarily for demos -- write an ADR before making permanent."
}

variable "max_instances" {
  type        = number
  default     = 1
  description = "Maximum instances. Capped at 1 until cost model justifies horizontal scaling. See ADR-0011."
}

variable "concurrency" {
  type        = number
  default     = 1
  description = "Max concurrent requests per instance. 1 ensures GPU memory is not split across parallel vLLM calls at MVP scale. Increase only after benchmarking VRAM under load."
}

variable "timeout_seconds" {
  type        = number
  default     = 300
  description = "Per-request timeout (seconds). 300s matches the POC value; large agentic prompts may need tuning."
}

# Startup probe
# vLLM cold start: CUDA init + AWQ model load + warmup ~20-60s (ADR-0011).
# initial_delay_seconds = 60 gives vLLM room to finish without premature failure.
# With period=10, failure_threshold=12 -> total window = 60 + 120 = 180s max.

variable "startup_probe_initial_delay" {
  type        = number
  default     = 60
  description = "Seconds before first startup probe check. Matches vLLM cold-start window (~60s, ADR-0011)."
}

variable "startup_probe_period" {
  type        = number
  default     = 10
  description = "Seconds between startup probe retries."
}

variable "startup_probe_failure_threshold" {
  type        = number
  default     = 12
  description = "Failures before the instance is killed. With period=10 this gives 120s of probing after initial_delay."
}

variable "startup_probe_timeout" {
  type        = number
  default     = 10
  description = "Seconds each probe attempt may take before counted as failed."
}

# Environment

variable "env" {
  type        = map(string)
  default     = {}
  description = "Non-secret environment variables passed to the container."
}

# IAM

variable "invoker_members" {
  type        = list(string)
  default     = []
  description = "IAM members granted roles/run.invoker. 'allUsers' requires an ADR (CLAUDE.md s3.4)."
}
