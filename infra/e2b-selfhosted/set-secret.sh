#!/usr/bin/env bash
# Store the self-hosted E2B team API key (from Secrets Manager, written by finalize.sh) and E2B_DOMAIN in the
# Kubernetes Secret used by the trainer pods. The key is passed through a pipe and never printed or written to disk.
# HF_TOKEN is taken from the environment, or kept from the existing Secret when it is not set.
#
#   E2B_DOMAIN=e2b.example.com ./infra/e2b-selfhosted/set-secret.sh
set -euo pipefail
export AWS_REGION="${AWS_REGION:-us-west-2}"
E2B_DOMAIN="${E2B_DOMAIN:?set E2B_DOMAIN (for example e2b.example.com)}"
SECRET_ID="${SECRET_ID:-harbor-rl-e2b/team-api-key}"
NS=harbor-rl

KEY="$(aws secretsmanager get-secret-value --secret-id "$SECRET_ID" --region "$AWS_REGION" \
  --query SecretString --output text)"
[ -n "$KEY" ] || { echo "secret $SECRET_ID is empty; run finalize.sh first"; exit 1; }
HF_TOKEN="${HF_TOKEN:-$(kubectl -n "$NS" get secret sandbox-secrets -o jsonpath='{.data.HF_TOKEN}' 2>/dev/null | base64 -d 2>/dev/null || true)}"

KEY="$KEY" HF_TOKEN="$HF_TOKEN" E2B_DOMAIN="$E2B_DOMAIN" python3 - "$NS" <<'PY' | kubectl apply --server-side --force-conflicts --field-manager=harbor-rl -f - >/dev/null  # server-side: no last-applied copy of the data
import base64, json, os, sys
data = {"E2B_API_KEY": os.environ["KEY"], "E2B_DOMAIN": os.environ["E2B_DOMAIN"]}
if os.environ.get("HF_TOKEN"):
    data["HF_TOKEN"] = os.environ["HF_TOKEN"]
print(json.dumps({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                  "metadata": {"name": "sandbox-secrets", "namespace": sys.argv[1]},
                  "data": {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}}))
PY
echo "sandbox-secrets updated (E2B_API_KEY, E2B_DOMAIN${HF_TOKEN:+, HF_TOKEN})"
