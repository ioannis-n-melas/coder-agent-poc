variable "project_id" { type = string }
variable "region" { type = string }
variable "service_name" { type = string }
variable "image" { type = string }
variable "service_account" { type = string }

variable "cpu" {
  type    = string
  default = "1"
}
variable "memory" {
  type    = string
  default = "512Mi"
}
variable "min_instances" {
  type    = number
  default = 0
}
variable "max_instances" {
  type    = number
  default = 3
}
variable "concurrency" {
  type    = number
  default = 8
}
variable "timeout_seconds" {
  type    = number
  default = 300
}

variable "env" {
  type        = map(string)
  default     = {}
  description = "Non-secret env vars"
}

variable "startup_probe_initial_delay" {
  type    = number
  default = 5
}
variable "startup_probe_timeout" {
  type    = number
  default = 10
}

variable "invoker_members" {
  type        = list(string)
  default     = []
  description = "IAM members granted roles/run.invoker. Use 'allUsers' only with an ADR."
}

resource "google_cloud_run_v2_service" "service" {
  project  = var.project_id
  name     = var.service_name
  location = var.region

  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = var.service_account
    timeout         = "${var.timeout_seconds}s"

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    max_instance_request_concurrency = var.concurrency

    containers {
      image = var.image

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle          = var.min_instances == 0
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

      startup_probe {
        initial_delay_seconds = var.startup_probe_initial_delay
        timeout_seconds       = var.startup_probe_timeout
        period_seconds        = 10
        failure_threshold     = 10
        tcp_socket {
          port = 8080
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      # Cloud Run adds its own labels we don't want to churn on
      client,
      client_version,
    ]
  }
}

# Invoker bindings — one resource per member for clean diffs
resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = toset(var.invoker_members)

  project  = google_cloud_run_v2_service.service.project
  location = google_cloud_run_v2_service.service.location
  name     = google_cloud_run_v2_service.service.name
  role     = "roles/run.invoker"
  member   = each.value
}

output "url" {
  value = google_cloud_run_v2_service.service.uri
}

output "name" {
  value = google_cloud_run_v2_service.service.name
}

output "service_account" {
  value = var.service_account
}
