# Runbook

Operational playbook for the POC. Every lifecycle op has a script — this file documents when to run each one and how to debug when things break.

## Lifecycle

### One-time bootstrap
```bash
./scripts/check-prereqs.sh     # verify gcloud, terraform, uv, docker
./scripts/bootstrap-gcp.sh     # create Terraform state bucket, enable APIs, set billing alerts
```

### Build & push images
```bash
./scripts/build-and-push.sh             # both services
./scripts/build-and-push.sh model-server
./scripts/build-and-push.sh coder-agent
```

### Deploy
```bash
./scripts/deploy.sh plan       # terraform plan — always review first
./scripts/deploy.sh apply      # terraform apply
./scripts/deploy.sh output     # print service URLs and other outputs
```

### Smoke test
```bash
./scripts/smoke-test.sh        # curl the deployed endpoint with an ID token, verify a chat completion
```

### Tear down (keeps the GCP project + Terraform state)
```bash
./scripts/teardown.sh          # removes Cloud Run services + SAs
```

## Regions

Both services run in `europe-west4` per [ADR-0014](adr/0014-consolidate-model-server-to-europe-west4.md) (which superseded ADR-0011's regional split once Cloud Run L4 GPU went GA in europe-west4). Single region → single AR repo → no cross-region egress. If a future GPU SKU isn't available in europe-west4, ADR-0014 lists the triggers to revisit.

## Cost trap — cold agent + cold model-server

With `min_instances=0` on both services, a user hitting a fully-idle stack pays for:
1. coder-agent cold start (~1–3 s).
2. model-server cold start (~20–60 s; ADR-0011) — vLLM warmup + CUDA graph capture + weight paging.
3. First-token inference on a warmed L4.

On a demo day, a single long `/chat` request to a cold stack can easily consume 10+ minutes of L4 time before a first token reaches the user (counting retries if someone gives up and re-tries). Budget alerts at 50/90/100% of `var.monthly_budget_usd` catch this after the fact — but if you're about to demo, warm with a preceding `/health` probe or temporarily set `min_instances=1` on model-server.

### Local dev
```bash
./scripts/dev.sh up            # docker compose up model-server + coder-agent
./scripts/dev.sh test          # pytest across services
./scripts/dev.sh lint          # ruff + mypy
./scripts/dev.sh logs          # tail both services
./scripts/dev.sh down          # stop
```

## Cost

### Check current spend
```bash
gcloud billing accounts list
gcloud alpha billing accounts get-iam-policy "$GCP_BILLING_ACCOUNT"  # from .env
```

Or use the console: https://console.cloud.google.com/billing

### Set a hard budget cap
Terraform creates a billing budget that alerts at 50% / 90% / 100% of a configurable threshold. See [infra/terraform/modules/budget/](../infra/terraform/modules/budget/). The threshold is in `terraform.tfvars` (`monthly_budget_usd`).

## Billing kill switch

Implemented in `module.billing_hard_cap` ([ADR-0015](adr/0015-billing-hard-cap.md)). A Cloud Function (gen2) is triggered by a Pub/Sub notification from a billing-account-scoped budget. When billing-account spend crosses £500 (100% of `var.billing_hard_cap_amount`), the function calls `UpdateProjectBillingInfo` to disable billing on **every project attached to the billing account**.

### How it behaves

1. GCP sends a Pub/Sub message to `billing-hard-cap-alert` topic when spend crosses 100% of the configured amount.
2. Cloud Functions gen2 (`billing-kill-switch`) receives the message via Eventarc.
3. The function checks `costAmount >= budgetAmount`. If true and `DRY_RUN=false`, it lists all projects on the billing account and sets `billingEnabled=False` on each.
4. All Cloud Run services, Cloud Functions, and other billed resources stop incurring charges within ~1 minute of billing being disabled.

### Recovery after the kill switch fires

Re-enable billing on each project. You can do this one of two ways:

**Via `gcloud` (recommended for scripting):**
```bash
# List projects on the billing account to find affected ones:
gcloud billing projects list --billing-account=XXXXXX-XXXXXX-XXXXXX

# Re-enable billing on each project:
gcloud billing projects link coder-agent-poc-2026 \
  --billing-account=XXXXXX-XXXXXX-XXXXXX
```

**Via the Cloud Console:**
Go to https://console.cloud.google.com/billing -> My projects -> find the project -> Actions -> Change billing -> select the billing account -> Set account.

After re-enabling billing, Cloud Run services will start responding again immediately on the next request (scale-to-zero means no restart needed — they just weren't billed while billing was disabled, but they weren't deleted).

**Raise the budget before re-enabling** (strongly recommended): update `billing_hard_cap_amount` in `terraform.tfvars` to a higher value and run `terraform apply -target=module.billing_hard_cap` before re-enabling billing, otherwise the function will fire again immediately on the next budget cycle evaluation.

### Temporarily disabling the kill switch (for a known-expensive burst)

Option 1 — raise the budget threshold:
```bash
# Edit infra/terraform/terraform.tfvars: set billing_hard_cap_amount = 1000
terraform apply -target=module.billing_hard_cap
```

Option 2 — arm DRY_RUN (function logs but does not kill):
```bash
gcloud functions deploy billing-kill-switch \
  --region=europe-west4 \
  --update-env-vars=DRY_RUN=true \
  --project=coder-agent-poc-2026
```
Remember to re-arm (`DRY_RUN=false`) and restore the budget when the burst is over. If you change it via `gcloud` rather than Terraform, run `terraform apply -target=module.billing_hard_cap` afterwards to reconcile state.

Option 3 — pause the Pub/Sub subscription:
The Cloud Functions gen2 Eventarc trigger uses an internal Pub/Sub subscription managed by Eventarc. Pausing it directly is not supported; use Option 1 or 2 instead.

### Testing without firing the kill switch (dry-run end-to-end test)

The function has a `DRY_RUN` environment variable. With `DRY_RUN=true`, it logs what it would do but does not call `UpdateProjectBillingInfo`.

**Test procedure:**
```bash
# 1. Temporarily set DRY_RUN=true (via Terraform or gcloud, see above).

# 2. Publish a crafted mock message where costAmount < budgetAmount
#    to verify the function handles the "no action" path cleanly:
gcloud pubsub topics publish billing-hard-cap-alert \
  --project=coder-agent-poc-2026 \
  --message='{"costAmount": 100, "budgetAmount": 500, "budgetDisplayName": "test", "currencyCode": "GBP"}'

# 3. Confirm in Cloud Logging that the function received the message and
#    logged "Cost is below budget. No action taken."

# 4. Publish a mock message where costAmount >= budgetAmount (DRY_RUN=true,
#    so no billing is disabled):
gcloud pubsub topics publish billing-hard-cap-alert \
  --project=coder-agent-poc-2026 \
  --message='{"costAmount": 500, "budgetAmount": 500, "budgetDisplayName": "test", "currencyCode": "GBP"}'

# 5. Confirm in Cloud Logging:
#    - "KILL SWITCH TRIGGERED" is logged.
#    - "DRY_RUN=true — would disable billing but taking no action." is logged.
#    - Billing remains enabled on the project.

# 6. Re-arm: set DRY_RUN=false.
```

Check logs:
```bash
gcloud functions logs read billing-kill-switch \
  --region=europe-west4 \
  --project=coder-agent-poc-2026 \
  --limit=50
```

### What costs money in this MVP
- **Cloud Run GPU (model-server, L4)** — ~$0.90/hr per instance when warm (ADR-0011). Scale-to-zero means $0 when idle. At 8 active hrs/day × 30 days ≈ $216/mo.
- **Cloud Run CPU (coder-agent)** — vCPU-seconds while a request is in flight. ~$0.000018/vCPU-s + memory. Scale-to-zero; idle = $0.
- **Artifact Registry** — $0.10/GiB/month. The vLLM CUDA image is ~10–15 GiB in a single europe-west4 repo ≈ $1.00–1.50/mo.
- **Cloud Storage** (tfstate bucket) — pennies.
- **Network egress** — both services are co-located in europe-west4 (ADR-0014), so agent↔model traffic stays intra-region (no egress cost).
- **Budget alerts** fire at 50/90/100% of `var.monthly_budget_usd` (default $300).

## Debugging

### Cloud Run service not starting
```bash
gcloud run services describe coder-agent --region=europe-west4 --project=coder-agent-poc-2026
gcloud run services logs read coder-agent --region=europe-west4 --project=coder-agent-poc-2026 --limit=50
```

Common causes:
- Image failed to pull → check Artifact Registry permissions + image URI.
- Container exited → check `CMD` / `ENTRYPOINT` and port binding (must use `$PORT`).
- OOM → bump memory in `terraform.tfvars` (`model_server_memory`).

### Cold start too slow
vLLM warmup on L4 takes ~20–60 s (ADR-0011): CUDA init + AWQ weight paging + graph capture. Mitigations:
- Set `min_instances=1` on model-server for active demos (~$650/mo continuous; use sparingly).
- Warm with a `/health` probe 30–60 s before a demo request.
- Drop `MAX_MODEL_LEN` (default 32768) to 24576 or 16384 — smaller KV cache → faster warmup and less VRAM pressure.
- Set `ENFORCE_EAGER=true` to skip CUDA graph capture (trades steady-state throughput for faster cold start).

### coder-agent can't reach model-server
Verify IAM binding:
```bash
gcloud run services get-iam-policy model-server --region=europe-west4 --project=coder-agent-poc-2026
```
`coder-agent-sa@coder-agent-poc-2026.iam.gserviceaccount.com` must have `roles/run.invoker`.

### Deploy fails with "service account does not have permission"
Re-run `./scripts/bootstrap-gcp.sh` — it's idempotent and re-applies IAM.

## On-call contacts

- **Owner**: [ioannis-n-melas](https://github.com/ioannis-n-melas)
- **GCP project**: see `terraform.tfvars` (`project_id`)
- **Billing account**: see `terraform.tfvars` (`billing_account_id`) — `gcloud billing accounts list`
- **Repo**: https://github.com/ioannis-n-melas/coder-agent-poc
