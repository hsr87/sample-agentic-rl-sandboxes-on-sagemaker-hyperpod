#!/usr/bin/env bash
# Submit a one-off Kubernetes Job in the trainer image.
#   infra/k8s/submit.sh <job-name> <gpus> <command...>
# e.g. infra/k8s/submit.sh oracle-agentcore 0 python3 bench/oracle_check.py --sandbox agentcore
set -euo pipefail
export AWS_REGION="${AWS_REGION:-us-west-2}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export JOB_NAME="$1" GPUS="$2"; shift 2
export IMAGE="${IMAGE:-${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/harbor-rl/trainer:${TAG:?set TAG (trainer image tag)}}"
export AGENTCORE_RUNTIME_ARN="${AGENTCORE_RUNTIME_ARN:-}"  # needed only for --sandbox agentcore
# 1 = the runtime runs in VPC mode on subnets without internet (agentcore/deploy_runtime.sh does this)
export AGENTCORE_NETWORK_ISOLATED="${AGENTCORE_NETWORK_ISOLATED:-1}"
export RESULTS_S3_URI="${RESULTS_S3_URI:-s3://harbor-rl-sandbox-${ACCOUNT_ID}-${AWS_REGION}/results}"
export COMMAND="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "$@")"
HERE="$(cd "$(dirname "$0")" && pwd)"
envsubst < "$HERE/job.yaml" | kubectl apply -f -
echo "logs: kubectl -n harbor-rl logs -f job/${JOB_NAME}"
