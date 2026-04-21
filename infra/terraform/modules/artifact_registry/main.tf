variable "project_id" { type = string }
variable "region" { type = string }
variable "repository_name" { type = string }

resource "google_artifact_registry_repository" "repo" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_name
  description   = "Coder agent POC Docker images"
  format        = "DOCKER"

  cleanup_policies {
    id     = "keep-last-5-versions"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }

  cleanup_policies {
    id     = "delete-untagged-after-7d"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s"
    }
  }
}

output "repository_url" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_name}"
}

output "repository_id" {
  value = google_artifact_registry_repository.repo.id
}
