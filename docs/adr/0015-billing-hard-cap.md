# 0015 — Billing hard-cap kill-switch via Pub/Sub + Cloud Function

- **Status**: Accepted
- **Date**: 2026-04-21
- **Authors**: @ioannis-n-melas
- **Deciders**: @ioannis-n-melas

## Context

GCP billing budgets are alerting tools only — they never stop spend. A billing alert at 100% of budget fires an email/Pub/Sub notification but does not prevent charges from accruing. The project is about to deploy an NVIDIA L4 GPU on Cloud Run (~£0.90/hr). A runaway GPU with no kill mechanism could produce a multi-thousand-pound bill before the owner notices.

The user confirmed:
- All GCP projects on the billing account are experimental (single owner, no production traffic).
- Collective shutdown of all projects on the account when spend crosses £500 is acceptable.
- The priority is "no surprise bill" over "maximum availability."

GCP's canonical pattern for this (documented at https://cloud.google.com/billing/docs/how-to/notify#cap_disable_billing_to_stop_usage) is to attach a Pub/Sub topic to a billing budget threshold rule, then wire a Cloud Function to the topic that calls `UpdateProjectBillingInfo` to set `billingEnabled=False` on each project.

## Options considered

### Option A — Pub/Sub + Cloud Function (kill-switch)

The canonical GCP pattern.

- Pros: automated, runs within seconds of the budget threshold being crossed; no human action required; entirely serverless (Cloud Functions gen2, scale-to-zero); fully codified in Terraform; reversible (re-enable billing manually in < 1 minute).
- Cons: blast radius is the whole billing account (all projects go dark); requires `roles/billing.admin` on the billing account for the function's SA; has a latency of up to ~10 minutes between spend crossing the threshold and the budget notification firing (GCP budget notification SLA).

### Option B — Manual spend monitoring + alert emails only

Keep the existing `module.budget` email alerts and rely on the operator to manually disable billing when alerted.

- Pros: no automated blast radius, simpler infra.
- Cons: requires a human to be online and respond. At £0.90/hr, a 12-hour weekend outage of attention while the GPU is stuck on = ~£11. A runaway infinite loop = hundreds of pounds before Monday. Not acceptable for an unattended POC.

### Option C — Per-project budget with Cloud Run service suspension

Use the Cloud Run Admin API to delete or suspend the GPU service when spend crosses a per-project threshold.

- Pros: surgical — only the expensive service is stopped, other projects unaffected.
- Cons: requires a custom Cloud Function that knows which service to suspend; Cloud Run suspension is not atomic (in-flight requests continue); does not prevent charges from other services on the project; significantly more complex to implement and test. The simplicity trade-off is not worth it at POC scale.

### Option D — Cloud Run anomaly alerting (Ops Agent)

Use Cloud Monitoring alert policies on GPU utilisation or Cloud Run request rate to detect anomalies and auto-scale to zero.

- Pros: targeted, no blast radius.
- Cons: anomaly detection is probabilistic and tuning-intensive; does not address the core problem (a legitimately high-use period looks the same as a billing runaway to the anomaly detector); does not actually stop billing, only reduces it.

## Decision

**Option A — billing-account-scoped Pub/Sub + Cloud Function kill-switch at £500 GBP.**

Specifics:
- Budget threshold: 100% of £500 GBP (`kill_threshold_percent = 1.0`).
- Scope: billing account (all projects on the account), not just `coder-agent-poc-2026`. This matches the blast radius the user explicitly accepted.
- The existing `module.budget` (project-scoped, email alerts at 50/90/100% of $300 USD) is retained and co-exists. The two budgets serve different purposes:
  - `module.budget`: early-warning email alerts at the project level, in USD (matches the existing cost model commentary).
  - `module.billing_hard_cap`: automated termination at the account level, in GBP (matches the user's billing currency and the hard-cap intent).
- The function SA has `roles/billing.admin` on the billing account. This is the minimum role required — there is no finer-grained permission that allows `UpdateProjectBillingInfo`.
- `DRY_RUN=false` in production (armed). Set `DRY_RUN=true` in the function's environment variables to test without triggering.

### Deploy path

Because the current Terraform state has model-server and coder-agent not yet applied (pending real image digests), the kill-switch should be applied standalone:

```bash
terraform apply -target=module.billing_hard_cap
```

This creates: Pub/Sub topic, billing budget, Cloud Function gen2, SA, IAM bindings, GCS source bucket — without touching the Cloud Run services.

### UI budget reconciliation

The user has a manually-created budget named "total" scoped to the billing account at £500. Before running `terraform apply`, delete it:

1. Console: https://console.cloud.google.com/billing -> Budgets & alerts -> select "total" -> Delete.
2. OR leave it: two budgets at the same threshold will both notify the topic, triggering the function twice. Idempotent (billing is already disabled after the first call), but noisy.

Recommended: delete before apply.

## Consequences

- **Good**: automated spending hard cap — no human response required at 3am.
- **Good**: fully codified in Terraform; reproducible; version-controlled.
- **Good**: `DRY_RUN` flag allows safe end-to-end testing.
- **Good**: `module.budget` email alerts still provide early-warning at 50/90% of the lower USD threshold.
- **Bad**: blast radius is the entire billing account. Any other experimental projects on the account will also have billing disabled when the cap fires.
- **Bad**: GCP budget notification latency is up to ~10 minutes. In a worst-case GPU runaway, up to ~£0.15 of charges can accrue after crossing £500 before the function fires.
- **Bad**: the function SA has `roles/billing.admin` at the billing-account level. This is a high-privilege SA — it must never be used for anything else, and its key material must never be exported (Terraform uses Google-managed SA credentials, no key file is generated).
- **Trigger to revisit**: (a) a second non-experimental project is added to the billing account — revisit blast radius acceptability; (b) GCP adds a finer-grained permission that allows disabling billing without full `billing.admin`; (c) the budget amount needs to change — update `var.billing_hard_cap_amount` in `terraform.tfvars` and re-apply.

## References

- [GCP: Cap billing to stop usage](https://cloud.google.com/billing/docs/how-to/notify#cap_disable_billing_to_stop_usage)
- [ADR-0011 — Cloud Run with NVIDIA L4 GPU](0011-cloud-run-l4-gpu.md) — cost forcing function
- [ADR-0014 — Consolidate to europe-west4](0014-consolidate-model-server-to-europe-west4.md) — region context
- [infra/terraform/modules/billing_hard_cap/](../../infra/terraform/modules/billing_hard_cap/)
- [docs/RUNBOOK.md — Billing kill switch section](../RUNBOOK.md)
