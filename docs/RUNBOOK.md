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

## Regional split (ADR-0011)

Cloud Run GPU (NVIDIA L4) is not available in `europe-west4` as of 2026-04, so the MVP splits services across regions:

| Service       | Region        | Reason |
|---|---|---|
| `coder-agent` | `europe-west4` | Co-located with the developer (ADR-0004). |
| `model-server`| `us-central1`  | Cloud Run L4 GPU availability. |

**Cross-region latency:** every `coder-agent → model-server` HTTP call incurs ~100–130 ms RTT. A typical agentic task issues 5–15 model calls, adding ~1–2 s end-to-end wall time on top of inference. Acceptable for MVP; revisit if agent loops grow longer.

**Cross-region egress cost:** billed at ~$0.01/GiB within GCP. Agent↔model traffic is text-only (~5 KB per request); 1000 requests/day ≈ 5 MB/day ≈ $0.0015/mo. Negligible.

**When to consolidate back:** when Cloud Run GPU lands in `europe-west4`, update [ADR-0011](adr/0011-cloud-run-l4-gpu.md) and collapse `var.model_server_region` into `var.region`.

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

### What costs money in this MVP
- **Cloud Run GPU (model-server, L4)** — ~$0.90/hr per instance when warm (ADR-0011). Scale-to-zero means $0 when idle. At 8 active hrs/day × 30 days ≈ $216/mo.
- **Cloud Run CPU (coder-agent)** — vCPU-seconds while a request is in flight. ~$0.000018/vCPU-s + memory. Scale-to-zero; idle = $0.
- **Artifact Registry** — $0.10/GiB/month. The vLLM CUDA image is ~10–15 GiB per repo × 2 repos (europe-west4 + us-central1) ≈ $2–3/mo.
- **Cloud Storage** (tfstate bucket) — pennies.
- **Network egress** — cross-region coder-agent→model-server chatter is text-only, ~$0.0015/mo at 1000 req/day.
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
Verify IAM binding (note: model-server lives in `us-central1` — see **Regional split** above):
```bash
gcloud run services get-iam-policy model-server --region=us-central1 --project=coder-agent-poc-2026
```
`coder-agent-sa@coder-agent-poc-2026.iam.gserviceaccount.com` must have `roles/run.invoker`.

### Deploy fails with "service account does not have permission"
Re-run `./scripts/bootstrap-gcp.sh` — it's idempotent and re-applies IAM.

## On-call contacts

- **Owner**: [ioannis-n-melas](https://github.com/ioannis-n-melas)
- **GCP project**: see `terraform.tfvars` (`project_id`)
- **Billing account**: see `terraform.tfvars` (`billing_account_id`) — `gcloud billing accounts list`
- **Repo**: https://github.com/ioannis-n-melas/coder-agent-poc
