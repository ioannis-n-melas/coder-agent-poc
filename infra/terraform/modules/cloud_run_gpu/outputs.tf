output "url" {
  description = "The Cloud Run service URL"
  value       = google_cloud_run_v2_service.service.uri
}

output "name" {
  description = "The Cloud Run service name"
  value       = google_cloud_run_v2_service.service.name
}

output "service_account" {
  description = "Runtime service account email"
  value       = var.service_account
}

output "region" {
  description = "Region where this service is deployed (may differ from coder-agent region)"
  value       = google_cloud_run_v2_service.service.location
}
