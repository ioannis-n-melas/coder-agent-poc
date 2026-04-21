output "model_server_url" {
  description = "Cloud Run URL of the model-server"
  value       = module.model_server.url
}

output "coder_agent_url" {
  description = "Cloud Run URL of the coder-agent"
  value       = module.coder_agent.url
}

output "coder_agent_sa" {
  description = "Service account email for coder-agent"
  value       = module.iam.coder_agent_sa_email
}

output "model_server_sa" {
  description = "Service account email for model-server"
  value       = module.iam.model_server_sa_email
}

output "artifact_registry_repo" {
  description = "Artifact Registry repository URI"
  value       = module.artifact_registry.repository_url
}

output "artifacts_bucket" {
  description = "Cloud Storage bucket for agent artifacts"
  value       = module.storage.artifacts_bucket_name
}

output "smoke_test_command" {
  description = "Paste this to run a smoke test from your machine"
  value       = "curl -H \"Authorization: Bearer $(gcloud auth print-identity-token --audiences=${module.coder_agent.url})\" ${module.coder_agent.url}/health"
}
