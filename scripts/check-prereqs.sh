#!/usr/bin/env bash
# Verify local dev prerequisites are installed.
set -euo pipefail

fail=0

check() {
  local cmd="$1" hint="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "  ✓ $cmd — $("$cmd" --version 2>&1 | head -n 1)"
  else
    echo "  ✗ $cmd — missing. $hint"
    fail=1
  fi
}

echo "Checking prerequisites..."
check gcloud   "Install: https://cloud.google.com/sdk/docs/install"
check gh       "Install: brew install gh"
check terraform "Install: brew install terraform"
check uv       "Install: brew install uv  (or: curl -LsSf https://astral.sh/uv/install.sh | sh)"
check docker   "Install: Docker Desktop (https://docs.docker.com/desktop/)"
check jq       "Install: brew install jq"

echo ""
echo "Checking auth..."
if gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | grep -q .; then
  echo "  ✓ gcloud authenticated as: $(gcloud config get-value account 2>/dev/null)"
else
  echo "  ✗ gcloud not authenticated. Run: gcloud auth login && gcloud auth application-default login"
  fail=1
fi

if gh auth status >/dev/null 2>&1; then
  echo "  ✓ gh authenticated as: $(gh api user --jq .login 2>/dev/null)"
else
  echo "  ✗ gh not authenticated. Run: gh auth login"
  fail=1
fi

if [[ $fail -ne 0 ]]; then
  echo ""
  echo "Some prerequisites missing — fix them above before continuing."
  exit 1
fi

echo ""
echo "All prerequisites OK."
