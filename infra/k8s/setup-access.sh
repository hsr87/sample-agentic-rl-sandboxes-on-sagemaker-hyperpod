#!/usr/bin/env bash
# Namespace, ServiceAccount, EKS Pod Identity role (AgentCore data plane on one runtime, results upload,
# ECR pull of the task base image for the E2B template build),
# and Kubernetes Secrets created from environment variables (values never touch disk).
# RUNTIME_ID (AgentCore runtime id) is optional: without it the AgentCore statement is left out of the role policy
# (E2B only, or AgentCore not deployed yet); re-run with RUNTIME_ID after deploying the runtime.
# Uses E2B_API_KEY (E2B Cloud) and HF_TOKEN if set. Existing Secret keys are kept.
set -euo pipefail
export AWS_REGION="${AWS_REGION:-us-west-2}"
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export BUCKET="harbor-rl-sandbox-${ACCOUNT_ID}-${AWS_REGION}"
export RUNTIME_ID="${RUNTIME_ID:-}"
export EKS_CLUSTER="$(aws sagemaker describe-cluster --cluster-name "${CLUSTER_NAME:-harbor-rl-hp}" --region "$AWS_REGION" \
  --query Orchestrator.Eks.ClusterArn --output text | awk -F/ '{print $NF}')"
ROLE=harbor-rl-trainer-pod
NS=harbor-rl
SA=trainer
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" --tags Key=Project,Value=harbor-rl-sandbox \
    --assume-role-policy-document "$(envsubst < "${ROOT}/infra/iam/trainer-pod-trust.json")" >/dev/null
fi
# Trust is (re)applied on every run: only pods of this cluster, namespace and service account can assume the role.
aws iam update-assume-role-policy --role-name "$ROLE" \
  --policy-document "$(envsubst < "${ROOT}/infra/iam/trainer-pod-trust.json")"
POLICY="$(envsubst < "${ROOT}/infra/iam/trainer-pod-policy.json" | RUNTIME_ID="$RUNTIME_ID" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
if not os.environ["RUNTIME_ID"]:
    d["Statement"] = [s for s in d["Statement"] if s.get("Sid") != "AgentCoreDataPlaneOnTaskRuntime"]
    print("note: RUNTIME_ID not set, AgentCore permissions left out", file=sys.stderr)
print(json.dumps(d))')"
aws iam put-role-policy --role-name "$ROLE" --policy-name trainer-pod --policy-document "$POLICY"

kubectl get ns "$NS" >/dev/null 2>&1 || kubectl create ns "$NS"
kubectl -n "$NS" get sa "$SA" >/dev/null 2>&1 || kubectl -n "$NS" create sa "$SA"

if ! aws eks list-pod-identity-associations --cluster-name "$EKS_CLUSTER" --namespace "$NS" --service-account "$SA" \
     --region "$AWS_REGION" --query 'associations[0].associationId' --output text | grep -q '^a-'; then
  aws eks create-pod-identity-association --cluster-name "$EKS_CLUSTER" --namespace "$NS" --service-account "$SA" \
    --role-arn "$(aws iam get-role --role-name "$ROLE" --query Role.Arn --output text)" \
    --tags Project=harbor-rl-sandbox --region "$AWS_REGION" >/dev/null
fi

# Secrets from environment variables, merged into the existing Secret so keys written by other scripts
# (E2B_DOMAIN and the self-hosted key from infra/e2b-selfhosted/set-secret.sh) are kept. Values go through
# environment variables and a pipe, never command-line arguments or files.
[ -n "${E2B_API_KEY:-}" ] || echo "note: E2B_API_KEY not set (expected for self-hosted E2B; set-secret.sh adds it)"
[ -n "${HF_TOKEN:-}" ] || echo "warning: HF_TOKEN not set"
EXISTING="$(kubectl -n "$NS" get secret sandbox-secrets -o json 2>/dev/null || echo '{}')"
EXISTING="$EXISTING" NS="$NS" python3 - <<'PY' | kubectl apply --server-side --force-conflicts --field-manager=harbor-rl -f - >/dev/null  # server-side: no last-applied copy of the data
import base64, json, os
data = json.loads(os.environ["EXISTING"]).get("data", {}) or {}
for k in ("E2B_API_KEY", "HF_TOKEN"):
    if os.environ.get(k):
        data[k] = base64.b64encode(os.environ[k].encode()).decode()
print(json.dumps({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                  "metadata": {"name": "sandbox-secrets", "namespace": os.environ["NS"]}, "data": data}))
PY
echo "namespace=$NS serviceaccount=$SA role=$ROLE"
