variable "project_id" { type = string }
variable "billing_account_id" { type = string }
variable "monthly_budget_usd" {
  # Misnomer kept for backwards compat — the value is interpreted in
  # var.currency_code (default GBP to match the billing account's own
  # currency; GCP rejects cross-currency budget specs with a 400).
  type = number
}
variable "currency_code" {
  type        = string
  default     = "GBP"
  description = "ISO 4217 currency for the budget amount. Must match the billing account's currency — GCP rejects mismatches with BadRequestException."
}
variable "alert_emails" { type = list(string) }

resource "google_monitoring_notification_channel" "email" {
  for_each = toset(var.alert_emails)

  project      = var.project_id
  display_name = "Budget alert: ${each.value}"
  type         = "email"
  labels = {
    email_address = each.value
  }
}

resource "google_billing_budget" "budget" {
  billing_account = var.billing_account_id
  display_name    = "${var.project_id} — monthly cap"

  budget_filter {
    projects = ["projects/${var.project_id}"]
  }

  amount {
    specified_amount {
      currency_code = var.currency_code
      units         = var.monthly_budget_usd
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }

  all_updates_rule {
    monitoring_notification_channels = [for c in google_monitoring_notification_channel.email : c.id]
    disable_default_iam_recipients   = false
  }
}

output "budget_id" {
  value = google_billing_budget.budget.name
}
