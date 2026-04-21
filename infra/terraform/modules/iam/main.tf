variable "project_id" { type = string }

# ── model-server service account ────────────────────────────────────
resource "google_service_account" "model_server" {
  project      = var.project_id
  account_id   = "model-server-sa"
  display_name = "model-server (Cloud Run)"
  description  = "Runs the llama.cpp model server. Minimal permissions — only reads its own image."
}

# Allow the SA to read its image from Artifact Registry (implicit via service agent for Cloud Run,
# explicit here for clarity if needed in other contexts).
# (Cloud Run's service agent handles image pulls; we don't grant this to the runtime SA.)

# ── coder-agent service account ─────────────────────────────────────
resource "google_service_account" "coder_agent" {
  project      = var.project_id
  account_id   = "coder-agent-sa"
  display_name = "coder-agent (Cloud Run)"
  description  = "Runs the DeepAgents FastAPI service. Can invoke model-server and read/write artifacts bucket."
}

# coder-agent can read artifacts bucket (grant at bucket level in storage module — here we wire
# IAM for project-level needs).
resource "google_project_iam_member" "coder_agent_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.coder_agent.email}"
}

resource "google_project_iam_member" "model_server_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.model_server.email}"
}

output "model_server_sa_email" {
  value = google_service_account.model_server.email
}

output "coder_agent_sa_email" {
  value = google_service_account.coder_agent.email
}
