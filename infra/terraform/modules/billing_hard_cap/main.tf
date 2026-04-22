########################################################################
# billing_hard_cap module
#
# Implements the canonical GCP billing kill-switch pattern:
#   google_billing_budget (billing-account scope)
#     -> Pub/Sub notification at kill_threshold_percent of budget_amount
#       -> Cloud Function gen2 (Python)
#         -> disables billing on every project attached to the billing account
#
# BLAST RADIUS: disabling billing at the billing-account level takes down
# ALL projects tied to that account, not just this one.  User confirmed
# this is acceptable because all projects on the account are experimental.
# See ADR-0015 for alternatives considered.
#
# RECOVERY: re-enable billing via:
#   gcloud billing projects link PROJECT_ID --billing-account=ACCOUNT_ID
# or via the Cloud Console (Billing -> My projects -> Re-enable).
########################################################################

# ── API enablement ───────────────────────────────────────────────────

resource "google_project_service" "cloudfunctions" {
  project            = var.project_id
  service            = "cloudfunctions.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  project            = var.project_id
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "pubsub" {
  project            = var.project_id
  service            = "pubsub.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbilling" {
  project            = var.project_id
  service            = "cloudbilling.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "run" {
  project            = var.project_id
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "eventarc" {
  project            = var.project_id
  service            = "eventarc.googleapis.com"
  disable_on_destroy = false
}

# ── Pub/Sub topic ────────────────────────────────────────────────────

resource "google_pubsub_topic" "billing_alert" {
  name    = "billing-hard-cap-alert"
  project = var.project_id

  depends_on = [google_project_service.pubsub]
}

# ── Billing budget (billing-account scope) ───────────────────────────
#
# Scoped to the whole billing account (no projects filter), so it
# captures spend across ALL attached projects — matching the kill-switch
# blast radius.
#
# IMPORTANT: if you have a UI-created budget named "total" on this
# billing account, DELETE it before running terraform apply so Terraform
# can own the canonical budget.  Two budgets with identical filters will
# both notify the topic, which is harmless but confusing.

resource "google_billing_budget" "hard_cap" {
  billing_account = var.billing_account_id
  display_name    = "billing-hard-cap — kill switch (TF-managed)"

  # No projects filter = all projects on the billing account.
  budget_filter {
    calendar_period = "MONTH"
  }

  amount {
    specified_amount {
      currency_code = var.budget_currency_code
      units         = tostring(floor(var.budget_amount))
    }
  }

  # Only the 100% threshold triggers the kill-switch.
  threshold_rules {
    threshold_percent = var.kill_threshold_percent
    spend_basis       = "CURRENT_SPEND"
  }

  all_updates_rule {
    pubsub_topic                   = google_pubsub_topic.billing_alert.id
    schema_version                 = "1.0"
    disable_default_iam_recipients = false
    # Notify even when spend is forecasted to exceed — belt-and-suspenders.
    enable_project_level_recipients = false
  }
}

# ── Service account for the Cloud Function ────────────────────────────

resource "google_service_account" "kill_switch_sa" {
  project      = var.project_id
  account_id   = "billing-kill-switch-sa"
  display_name = "Billing Kill Switch Function SA"
  description  = "Runs the billing-hard-cap Cloud Function. Has roles/billing.admin at billing-account level."
}

# Grant roles/billing.admin on the billing account so the function can
# call UpdateProjectBillingInfo to disable billing.
# This is intentionally broad — billing.admin is the minimum role that
# allows disabling billing on a project. There is no finer-grained role.
resource "google_billing_account_iam_member" "kill_switch_billing_admin" {
  billing_account_id = var.billing_account_id
  role               = "roles/billing.admin"
  member             = "serviceAccount:${google_service_account.kill_switch_sa.email}"
}

# Allow the function's SA to read its own project list via Resource Manager.
resource "google_project_iam_member" "kill_switch_project_viewer" {
  project = var.project_id
  role    = "roles/browser"
  member  = "serviceAccount:${google_service_account.kill_switch_sa.email}"
}

# ── Cloud Storage bucket for function source archive ─────────────────

resource "google_storage_bucket" "function_source" {
  name                        = "${var.project_id}-billing-kill-switch-src"
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  lifecycle_rule {
    action { type = "Delete" }
    condition { age = 7 }
  }
}

# Zip and upload the function source code.
data "archive_file" "function_source" {
  type        = "zip"
  source_dir  = "${path.module}/function"
  output_path = "${path.module}/.build/billing_kill_switch.zip"
}

resource "google_storage_bucket_object" "function_source" {
  name   = "billing_kill_switch_${data.archive_file.function_source.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.function_source.output_path
}

# ── Cloud Function gen2 ───────────────────────────────────────────────

resource "google_cloudfunctions2_function" "kill_switch" {
  name     = "billing-kill-switch"
  project  = var.project_id
  location = var.region

  description = "Disables billing on all projects when billing-account spend crosses the hard cap. See ADR-0015."

  build_config {
    runtime     = "python312"
    entry_point = "disable_billing_on_budget_alert"

    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_source.name
      }
    }
  }

  service_config {
    service_account_email = google_service_account.kill_switch_sa.email
    available_memory      = "256M"
    timeout_seconds       = 60
    min_instance_count    = 0
    max_instance_count    = 1

    environment_variables = {
      PROJECT_ID         = var.project_id
      BILLING_ACCOUNT_ID = var.billing_account_id
      # Set DRY_RUN=true to test the function without actually killing billing.
      # The function will log what it would do but not call UpdateProjectBillingInfo.
      DRY_RUN = "false"
    }
  }

  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic          = google_pubsub_topic.billing_alert.id
    retry_policy          = "RETRY_POLICY_DO_NOT_RETRY"
    service_account_email = google_service_account.kill_switch_sa.email
  }

  depends_on = [
    google_project_service.cloudfunctions,
    google_project_service.cloudbuild,
    google_project_service.run,
    google_project_service.eventarc,
    google_storage_bucket_object.function_source,
  ]
}

# Allow Pub/Sub to invoke the function (required for gen2 event trigger).
resource "google_cloud_run_service_iam_member" "pubsub_invoker" {
  project  = var.project_id
  location = var.region
  service  = google_cloudfunctions2_function.kill_switch.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.kill_switch_sa.email}"
}
