#!/usr/bin/env bash
# Build the AgentCore variant of the task image (arm64 + shim), create the execution role,
# and create (or update) one AgentCore Runtime for the whole task suite:
# platformVersion V2, VPC network mode on isolated subnets (no internet; agentcore/network.sh).
#
#   TAG=v2 ./agentcore/deploy_runtime.sh               # TAG = tag of harbor-rl/tasks-base to build on
#   TAG=v2 SKIP_BUILD=1 ./agentcore/deploy_runtime.sh  # reuse an already pushed tasks-agentcore:$TAG
#
# Requires AWS CLI >= 2.36.46 (--platform-version). Prints the runtime ARN at the end.
set -euo pipefail
export AWS_REGION="${AWS_REGION:-us-west-2}"
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
TAG="${TAG:?set TAG (tag of harbor-rl/tasks-base, e.g. v2)}"
BASE_IMAGE="${REGISTRY}/harbor-rl/tasks-base:${TAG}"
IMAGE="${REGISTRY}/harbor-rl/tasks-agentcore:${TAG}"
ROLE_NAME="harbor-rl-agentcore-exec"
export RUNTIME_NAME="${RUNTIME_NAME:-harbor_rl_tasks}"  # also scopes the execution role's log permissions
TAGS='Key=Project,Value=harbor-rl-sandbox'
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 1. Image: shared base (arm64 variant) + contract shim.
#    Docker equivalent: docker buildx build --platform linux/arm64 --build-arg BASE_IMAGE=... -t "$IMAGE" --push <ctx>
#    where <ctx> holds shim/main.go and warmup.sh (see below).
aws ecr describe-repositories --repository-names harbor-rl/tasks-agentcore --region "$AWS_REGION" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name harbor-rl/tasks-agentcore --region "$AWS_REGION" \
    --image-scanning-configuration scanOnPush=true --tags "$TAGS" >/dev/null
if [ -z "${SKIP_BUILD:-}" ]; then
  aws ecr get-login-password --region "$AWS_REGION" | finch login --username AWS --password-stdin "$REGISTRY"
  # Build context: the shim source plus the shared sandbox warm-up script (also used by the E2B templates).
  CTX="$(mktemp -d)"
  trap 'rm -rf "$CTX"' EXIT
  mkdir -p "$CTX/shim" && cp "$ROOT/agentcore/shim/main.go" "$CTX/shim/" && cp "$ROOT/tasks/image/warmup.sh" "$CTX/"
  finch build --platform linux/arm64 --build-arg BASE_IMAGE="$BASE_IMAGE" \
    -f "$ROOT/agentcore/image/Dockerfile" -t "$IMAGE" "$CTX"
  finch push --platform linux/arm64 "$IMAGE"
fi

# 2. Execution role (pull of this one image repository + runtime logs only). Code running in a session can read
#    these credentials, so keep the policy minimal. The policy is (re)applied on every run.
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE_NAME" --tags "$TAGS" \
    --assume-role-policy-document "$(envsubst < "$ROOT/infra/iam/agentcore-exec-trust.json")" >/dev/null
  NEW_ROLE=1
fi
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name agentcore-exec \
  --policy-document "$(envsubst < "$ROOT/infra/iam/agentcore-exec-policy.json")"
[ -n "${NEW_ROLE:-}" ] && sleep 10  # IAM propagation
ROLE_ARN="$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text)"

# 3. Isolated network (VPC mode, no internet route).
eval "$("$ROOT/agentcore/network.sh" | grep -E '^(SUBNETS|SESSION_SG)=')"
NETWORK="{\"networkMode\":\"VPC\",\"networkModeConfig\":{\"subnets\":[\"${SUBNETS//,/\",\"}\"],\"securityGroups\":[\"${SESSION_SG}\"]}}"

# 4. Runtime (one per image). V2 cold-starts sessions from a snapshot.
RUNTIME_ID="$(aws bedrock-agentcore-control list-agent-runtimes --region "$AWS_REGION" \
  --query "agentRuntimes[?agentRuntimeName=='${RUNTIME_NAME}'].agentRuntimeId | [0]" --output text)"
if [ "$RUNTIME_ID" = "None" ] || [ -z "$RUNTIME_ID" ]; then
  RUNTIME_ID="$(aws bedrock-agentcore-control create-agent-runtime --region "$AWS_REGION" \
    --agent-runtime-name "$RUNTIME_NAME" \
    --description "Harbor RL task sandbox (shared image ${TAG})" \
    --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"${IMAGE}\"}}" \
    --role-arn "$ROLE_ARN" \
    --network-configuration "$NETWORK" \
    --protocol-configuration '{"serverProtocol":"HTTP"}' \
    --lifecycle-configuration '{"idleRuntimeSessionTimeout":900,"maxLifetime":28800}' \
    --platform-version V2 \
    --tags Project=harbor-rl-sandbox \
    --query agentRuntimeId --output text)"
else
  # Existing runtime: point it at the (possibly new) image. This creates a new runtime version; the DEFAULT
  # endpoint follows the latest version.
  aws bedrock-agentcore-control update-agent-runtime --region "$AWS_REGION" --agent-runtime-id "$RUNTIME_ID" \
    --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"${IMAGE}\"}}" \
    --role-arn "$ROLE_ARN" \
    --network-configuration "$NETWORK" \
    --protocol-configuration '{"serverProtocol":"HTTP"}' \
    --lifecycle-configuration '{"idleRuntimeSessionTimeout":900,"maxLifetime":28800}' \
    --platform-version V2 >/dev/null
  sleep 10
fi

echo "Waiting for runtime ${RUNTIME_ID} to become READY..."
for _ in $(seq 1 120); do
  STATUS="$(aws bedrock-agentcore-control get-agent-runtime --region "$AWS_REGION" --agent-runtime-id "$RUNTIME_ID" --query status --output text)"
  [ "$STATUS" = "READY" ] && break
  case "$STATUS" in *FAILED*) echo "runtime status $STATUS"; aws bedrock-agentcore-control get-agent-runtime --region "$AWS_REGION" --agent-runtime-id "$RUNTIME_ID" --query failureReason --output text; exit 1;; esac
  sleep 15
done
aws bedrock-agentcore-control get-agent-runtime --region "$AWS_REGION" --agent-runtime-id "$RUNTIME_ID" \
  --query '[agentRuntimeArn,status,platformVersion]' --output text
