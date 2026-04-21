#!/usr/bin/env bash
# Smoke test against the deployed coder-agent.
#
# Acquires an ID token for the current user, calls /health and /chat, verifies
# the response. Exit 0 on success, non-zero on failure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
set -a; source "$REPO_ROOT/.env" 2>/dev/null || source "$REPO_ROOT/.env.example"; set +a

: "${GCP_PROJECT_ID:?}"
: "${GCP_REGION:?}"

CODER_AGENT_URL="$(gcloud run services describe coder-agent \
  --region="$GCP_REGION" \
  --project="$GCP_PROJECT_ID" \
  --format='value(status.url)' 2>/dev/null || true)"

if [[ -z "$CODER_AGENT_URL" ]]; then
  echo "✗ coder-agent not found in project=$GCP_PROJECT_ID region=$GCP_REGION"
  echo "  Deploy first: ./scripts/deploy.sh apply"
  exit 1
fi

echo "coder-agent URL: $CODER_AGENT_URL"

# Identity token for the active principal. Service accounts require --audiences;
# user accounts don't support --audiences (and don't need it — Cloud Run IAM
# checks the user's run.invoker role, not an audience claim).
ACTIVE_ACCOUNT="$(gcloud config get-value account 2>/dev/null)"
if [[ "$ACTIVE_ACCOUNT" == *".iam.gserviceaccount.com" ]]; then
  TOKEN="$(gcloud auth print-identity-token --audiences="$CODER_AGENT_URL")"
else
  TOKEN="$(gcloud auth print-identity-token)"
fi

# ── /health ────────────────────────────────────────────────────────
echo ""
echo "→ GET /health"
health_resp="$(curl -fsS -H "Authorization: Bearer $TOKEN" "$CODER_AGENT_URL/health")"
echo "  $health_resp"
echo "$health_resp" | jq -e '.status == "ok"' >/dev/null || { echo "✗ /health did not return status=ok"; exit 1; }
echo "  ✓ /health OK"

# ── /ready ─────────────────────────────────────────────────────────
echo ""
echo "→ GET /ready"
ready_resp="$(curl -fsS -H "Authorization: Bearer $TOKEN" "$CODER_AGENT_URL/ready")"
echo "  $ready_resp"
reachable="$(echo "$ready_resp" | jq -r '.model_server_reachable')"
if [[ "$reachable" != "true" ]]; then
  echo "  ⚠ model-server not reachable from coder-agent — check IAM binding"
fi

# ── /chat ──────────────────────────────────────────────────────────
echo ""
echo "→ POST /chat  (prompt: 'write a hello world in python')"
# CPU inference of a 1.5B model through DeepAgents can take 2–4 min on the
# first request (cold model + large system prompt). Give it 5 min.
chat_resp="$(curl -fsS --max-time 300 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Write a Python hello world. Return code only, no explanation."}' \
  "$CODER_AGENT_URL/chat")"

request_id="$(echo "$chat_resp" | jq -r '.request_id')"
output="$(echo "$chat_resp" | jq -r '.output')"

echo "  request_id: $request_id"
echo "  output ($(echo "$output" | wc -c) bytes):"
echo "  $output" | sed 's/^/    /'

if [[ -z "$output" || "$output" == "null" ]]; then
  echo "✗ empty output from /chat"
  exit 1
fi

echo ""
echo "✓ Smoke test passed."
