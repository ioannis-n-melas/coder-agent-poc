variable "project_id" { type = string }
variable "secrets" {
  type        = map(string)
  default     = {}
  description = "Map of secret_id -> description. Secret values are set out-of-band (gcloud or console)."
}

resource "google_secret_manager_secret" "secret" {
  for_each = var.secrets

  project   = var.project_id
  secret_id = each.key

  replication {
    auto {}
  }

  labels = {
    managed_by = "terraform"
  }
}

output "secret_ids" {
  value = [for s in google_secret_manager_secret.secret : s.secret_id]
}
