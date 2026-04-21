#!/usr/bin/env bash
# Smoke test against the deployed services.
#
# Acquires an ID token, calls coder-agent /health, /ready, and /chat.
# Also directly probes the model-server /health endpoint to verify the
# GPU service is up in its own region (us-central1).
#
# GPU cold start note (ADR-0011):
#   vLLM + CUDA + AWQ model load ≈ 20-60s. The /chat request uses a
#   --max-time of 360s (6 min) to survive a full cold start + inference.
#   If the model-server hasn't started yet, /ready on the coder-agent
#   will report model_server_reachable=false — this is expected on first
#   hit after scale-to-zero. The test will wait and retry.
#
# Exit 0 on success, non-zero on failure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
set -a; source "$REPO_ROOT/.env" 2>/dev/null || source "$REPO_ROOT/.env.example"; set +a

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID must be set in .env}"
: "${GCP_REGION:?GCP_REGION must be set in .env}"

# model-server lives in its own region (us-central1 per ADR-0011).
# Allow override via env var in case the GPU region changes later.
MODEL_SERVER_REGION="${MODEL_SERVER_REGION:-us-central1}"

# ── Discover service URLs ───────────────────────────────────────────
CODER_AGENT_URL="$(gcloud run services describe coder-agent \
  --region="$GCP_REGION" \
  --project="$GCP_PROJECT_ID" \
  --format='value(status.url)' 2>/dev/null || true)"

if [[ -z "$CODER_AGENT_URL" ]]; then
  echo "coder-agent not found in project=$GCP_PROJECT_ID region=$GCP_REGION"
  echo "  Deploy first: ./scripts/deploy.sh apply"
  exit 1
fi

MODEL_SERVER_URL="$(gcloud run services describe model-server \
  --region="$MODEL_SERVER_REGION" \
  --project="$GCP_PROJECT_ID" \
  --format='value(status.url)' 2>/dev/null || true)"

if [[ -z "$MODEL_SERVER_URL" ]]; then
  echo "model-server not found in project=$GCP_PROJECT_ID region=$MODEL_SERVER_REGION"
  echo "  Deploy first: ./scripts/deploy.sh apply"
  exit 1
fi

echo "coder-agent  URL : $CODER_AGENT_URL  (region: $GCP_REGION)"
echo "model-server URL : $MODEL_SERVER_URL  (region: $MODEL_SERVER_REGION)"
echo ""

# ── Acquire identity tokens ────────────────────────────────────────
ACTIVE_ACCOUNT="$(gcloud config get-value account 2>/dev/null)"

get_id_token() {
  local audience="$1"
  if [[ "$ACTIVE_ACCOUNT" == *".iam.gserviceaccount.com" ]]; then
    gcloud auth print-identity-token --audiences="$audience"
  else
    gcloud auth print-identity-token
  fi
}

AGENT_TOKEN="$(get_id_token "$CODER_AGENT_URL")"
MODEL_TOKEN="$(get_id_token "$MODEL_SERVER_URL")"

# ── 1. model-server /health (direct) ──────────────────────────────
echo "── model-server (direct) ──────────────────────────────────────"
echo "→ GET $MODEL_SERVER_URL/health"
echo "NOTE: If the GPU instance is cold this may take 20-60s (ADR-0011)."

ms_health_resp="$(curl -fsS \
  --max-time 90 \
  --retry 3 \
  --retry-delay 10 \
  --retry-connrefused \
  -H "Authorization: Bearer $MODEL_TOKEN" \
  "$MODEL_SERVER_URL/health")"
echo "  $ms_health_resp"
echo "  model-server /health OK"
echo ""

# ── 2. coder-agent /health ─────────────────────────────────────────
echo "── coder-agent ────────────────────────────────────────────────"
echo "→ GET /health"
health_resp="$(curl -fsS -H "Authorization: Bearer $AGENT_TOKEN" "$CODER_AGENT_URL/health")"
echo "  $health_resp"
echo "$health_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='ok', 'status != ok'" \
  || { echo "/health did not return status=ok"; exit 1; }
echo "  /health OK"
echo ""

# ── 3. coder-agent /ready ─────────────────────────────────────────
echo "→ GET /ready"
ready_resp="$(curl -fsS -H "Authorization: Bearer $AGENT_TOKEN" "$CODER_AGENT_URL/ready")"
echo "  $ready_resp"
reachable="$(echo "$ready_resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('model_server_reachable',''))")"
if [[ "$reachable" != "true" ]]; then
  echo "  WARNING: model-server not reachable from coder-agent."
  echo "    Possible causes: GPU cold start still in progress, IAM binding missing,"
  echo "    or cross-region connectivity issue. Check:"
  echo "    gcloud run services get-iam-policy model-server --region=$MODEL_SERVER_REGION --project=$GCP_PROJECT_ID"
fi
echo ""

# ── 4. /chat end-to-end ───────────────────────────────────────────
echo "→ POST /chat  (prompt: 'write a hello world in python')"
echo "NOTE: GPU cold start + vLLM warmup can add 20-60s to first token."
echo "      Timeout set to 360s to survive full cold-start + inference."

chat_resp="$(curl -fsS \
  --max-time 360 \
  -H "Authorization: Bearer $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Write a Python hello world. Return code only, no explanation."}' \
  "$CODER_AGENT_URL/chat")"

request_id="$(echo "$chat_resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('request_id',''))")"
output="$(echo "$chat_resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('output',''))")"

echo "  request_id : $request_id"
echo "  output ($(echo -n "$output" | wc -c) bytes):"
echo "$output" | sed 's/^/    /'

if [[ -z "$output" || "$output" == "None" ]]; then
  echo "empty output from /chat"
  exit 1
fi

echo ""
echo "Smoke test passed."
