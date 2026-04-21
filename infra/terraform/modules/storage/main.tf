variable "project_id" { type = string }
variable "region" { type = string }
variable "lifecycle_age_days" { type = number }

resource "google_storage_bucket" "artifacts" {
  project                     = var.project_id
  name                        = "${var.project_id}-artifacts"
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = false
  }

  lifecycle_rule {
    condition {
      age = var.lifecycle_age_days
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    purpose = "agent-artifacts"
    env     = "poc"
  }
}

output "artifacts_bucket_name" {
  value = google_storage_bucket.artifacts.name
}

output "artifacts_bucket_url" {
  value = google_storage_bucket.artifacts.url
}
