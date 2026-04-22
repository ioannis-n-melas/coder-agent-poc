########################################################################
# cloud_run_gpu/main.tf
#
# Cloud Run v2 (second-gen) service with NVIDIA L4 GPU support.
#
# Architecture notes:
#  - GPU requires second-gen execution environment (automatically enforced
#    by Cloud Run when node_selector accelerator is set).
#  - launch_stage = "GA" -- Cloud Run GPU with L4 is GA as of 2026-04
#    (confirmed in ADR-0011). No BETA annotation required.
#  - Region must support L4 Cloud Run GPU. europe-west4 is GA per ADR-0014
#    (supersedes ADR-0011 regional split).
#  - cpu_idle must be false when GPU is attached: Cloud Run keeps CPU/GPU
#    allocated during the full request even when awaiting tokens. Setting
#    cpu_idle=true on a GPU service causes provisioning errors.
#  - concurrency=1 by default: vLLM handles its own internal batching;
#    exposing multiple concurrent Cloud Run requests risks VRAM OOM at MVP.
########################################################################

resource "google_cloud_run_v2_service" "service" {
  project  = var.project_id
  name     = var.service_name
  location = var.region

  # GPU requires second-gen execution environment.
  # launch_stage GA -- Cloud Run L4 GPU is GA (not BETA) as of 2026-04.
  launch_stage = "GA"

  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = var.service_account
    timeout         = "${var.timeout_seconds}s"

    # EXECUTION_ENVIRONMENT_GEN2 is required for GPU on Cloud Run.
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

    # Zonal redundancy for GPU:
    #   Google currently (2026-04) grants zonal-redundancy L4 quota sparingly —
    #   "not available due to high demand, coming months" per the rejection
    #   email on the first quota request. The no-zonal-redundancy SKU was
    #   granted instead (1x L4 in europe-west4). Set to true to use the
    #   SKU we actually have quota for.
    #   Trade-off: if the hosting zone has an outage, the service goes down
    #   (no failover). Acceptable for a single-instance scale-to-zero POC.
    #   Flip back to false once Google grants zonal-redundancy quota.
    gpu_zonal_redundancy_disabled = var.gpu_zonal_redundancy_disabled

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    max_instance_request_concurrency = var.concurrency

    # GPU node selector
    # Selects the NVIDIA L4 accelerator SKU. This is the node-level
    # selector that tells Cloud Run's scheduler to place the instance
    # on an L4-equipped host.
    dynamic "node_selector" {
      for_each = var.gpu_enabled ? [1] : []
      content {
        accelerator = var.gpu_type
      }
    }

    containers {
      image = var.image

      resources {
        limits = merge(
          {
            cpu    = var.cpu
            memory = var.memory
          },
          # GPU limit -- only added when GPU is enabled.
          var.gpu_enabled ? { "nvidia.com/gpu" = tostring(var.gpu_count) } : {}
        )

        # cpu_idle=false: GPU service must keep CPU allocated throughout
        # the request lifecycle. Setting true on a GPU service causes errors.
        cpu_idle = false

        # startup_cpu_boost helps vLLM warm faster during cold start.
        startup_cpu_boost = true
      }

      ports {
        container_port = 8080
      }

      dynamic "env" {
        for_each = var.env
        content {
          name  = env.key
          value = env.value
        }
      }

      # Startup probe: generous window for vLLM cold start.
      # CUDA init + AWQ model load + vLLM warmup ~20-60s (ADR-0011).
      # initial_delay=60 + period=10 * failure_threshold=12 = 180s total window.
      startup_probe {
        initial_delay_seconds = var.startup_probe_initial_delay
        period_seconds        = var.startup_probe_period
        failure_threshold     = var.startup_probe_failure_threshold
        timeout_seconds       = var.startup_probe_timeout
        http_get {
          path = "/health"
          port = 8080
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      client,
      client_version,
    ]
  }
}

# Invoker IAM
resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = toset(var.invoker_members)

  project  = google_cloud_run_v2_service.service.project
  location = google_cloud_run_v2_service.service.location
  name     = google_cloud_run_v2_service.service.name
  role     = "roles/run.invoker"
  member   = each.value
}
