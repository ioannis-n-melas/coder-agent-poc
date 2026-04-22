output "function_url" {
  description = "HTTPS URL of the billing kill-switch Cloud Function (gen2). Not directly callable — triggered by Pub/Sub."
  value       = google_cloudfunctions2_function.kill_switch.service_config[0].uri
}

output "pubsub_topic_name" {
  description = "Full resource name of the Pub/Sub topic that triggers the kill-switch function."
  value       = google_pubsub_topic.billing_alert.id
}

output "kill_switch_sa_email" {
  description = "Service account email for the billing kill-switch function."
  value       = google_service_account.kill_switch_sa.email
}

output "budget_id" {
  description = "Terraform resource name of the billing budget (billing-account scope)."
  value       = google_billing_budget.hard_cap.name
}
