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

### What costs money in this POC
- **Cloud Run** — vCPU-seconds while a request is in flight. ~$0.000018/vCPU-s + memory. With scale-to-zero, idle = $0.
- **Artifact Registry** — $0.10/GiB/month for storage. Our images ≈ 1.5 GiB total → ~$0.15/mo.
- **Cloud Storage** (tfstate bucket) — pennies.
- **Network egress** — free for request/response bodies under the free tier.

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
llama.cpp mmap of the GGUF is the bottleneck. Options:
- Set `min_instances=1` (not free — costs ~$10–30/mo).
- Preload with `--mlock` (needs `memlock` capability — Cloud Run supports it).
- Smaller quant (Q3_K_S) — slightly worse quality, faster load.

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
