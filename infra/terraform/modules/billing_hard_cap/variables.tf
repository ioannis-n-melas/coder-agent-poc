variable "project_id" {
  description = "GCP project ID in which to deploy the Cloud Function and Pub/Sub topic."
  type        = string
}

variable "region" {
  description = "GCP region for the Cloud Function (gen2). Defaults to europe-west4 per ADR-0014."
  type        = string
  default     = "europe-west4"
}

variable "billing_account_id" {
  description = "GCP billing account ID (e.g. XXXXXX-XXXXXX-XXXXXX). Budget and IAM binding are scoped to this account."
  type        = string
}

variable "budget_amount" {
  description = "Monthly budget limit. When actual spend reaches kill_threshold_percent of this value, billing is disabled on every project attached to the billing account."
  type        = number
}

variable "budget_currency_code" {
  description = "ISO 4217 currency code for the budget amount (e.g. GBP, USD)."
  type        = string
  default     = "GBP"
}

variable "kill_threshold_percent" {
  description = "Fraction of budget_amount at which billing is disabled (1.0 = 100%). Triggers the kill-switch Pub/Sub notification."
  type        = number
  default     = 1.0
}
